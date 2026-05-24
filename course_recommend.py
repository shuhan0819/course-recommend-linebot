from fastapi import FastAPI, Request, HTTPException
from linebot.v3.messaging import (
    Configuration, AsyncApiClient, AsyncMessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhook import WebhookParser
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
import os, re, asyncio
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ── 模型 & 向量庫初始化 ──────────────────────────────
gpt_model = ChatOpenAI(model="gpt-4o-mini", openai_api_key=os.getenv("OPENAI_API_KEY"))
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vector_store = FAISS.load_local("faiss_index_recommand", embeddings, allow_dangerous_deserialization=True)
retriever = vector_store.as_retriever(
    search_type="mmr",
    search_kwargs={'k': 20, 'fetch_k': 20, 'lambda_mult': 0.5}
)

# ── LINE Bot 設定 ────────────────────────────────────
parser = WebhookParser(channel_secret=os.getenv("LINE_CHANNEL_SECRET"))
configuration = Configuration(access_token=os.getenv("LINE_ACCESS_TOKEN"))

# ── Prompt 定義 ──────────────────────────────────────
intent_prompt = ChatPromptTemplate.from_messages([
    ("human",
     "判斷以下使用者訊息的意圖，只能回覆以下三種之一：\n"
     "- RECOMMEND：使用者想詢問課程推薦、學習方向、職涯技能\n"
     "- GREETING：使用者在打招呼（嗨、哈囉、你好等）\n"
     "- IRRELEVANT：與課程推薦完全無關的問題\n\n"
     "使用者訊息：{user_question}\n"
     "只輸出一個詞，不要任何標點或說明。")
])

ability_prompt = ChatPromptTemplate.from_messages([
    ("human",
     "使用者問題: {user_question}\n"
     "請分析使用者想成為的角色或職業、有興趣的領域，列出該角色或領域可能需要的技能、知識或相關課程關鍵字。\n"
     "要求：\n"
     "1. 僅輸出關鍵字，每行一個或用逗號分隔。\n"
     "2. 不要任何說明文字、標題或其他多餘內容。\n"
     "3. 請保持簡短乾淨。\n"
     "4. 請使用繁體中文")
])

recommend_prompt = ChatPromptTemplate.from_messages([
    ("human",
     "以下是多筆課程資料，每筆包含課程名稱、教學目標與課程內容：\n\n{context}\n\n"
     "請依據使用者問題（{user_question}）判斷哪些課程最符合需求，"
     "請從中挑選最相關的 3 門課程進行推薦並說明推薦原因或可以學習到什麼內容。\n\n"
     "要求：\n1. 用繁體中文回答；\n"
     "2. 只推薦最相關的 3 門課，不多不少；\n"
     "3. 每一堂推薦課皆列出「課程名稱」、「推薦理由（1-2 行）」、「可學得技能/知識」。")
])

GREETING_RESPONSE = (
    "👋 哈囉！我是課程推薦小幫手！\n\n"
    "📚 我可以幫你：\n"
    "• 根據你想從事的職業或學習方向，推薦最適合的課程\n"
    "• 分析你需要具備哪些技能與知識\n\n"
    "💬 使用方式：\n"
    "直接告訴我你的目標，例如：\n"
    "「我想成為資料分析師，有哪些課程適合我？」\n"
    "「我對機器學習有興趣，推薦我相關課程」\n\n"
    "試試看吧！😊"
)

IRRELEVANT_RESPONSE = (
    "抱歉，我只能協助課程推薦相關的問題 📚\n"
    "如果你想了解適合自己的課程，歡迎告訴我你的學習目標或想從事的職業！"
)

# ── 核心邏輯函式 ─────────────────────────────────────

async def detect_intent(user_question: str) -> str:
    chain = intent_prompt | gpt_model | StrOutputParser()
    result = await chain.ainvoke({"user_question": user_question})
    return result.strip().upper()


def extract_keywords(text: str) -> list[str]:
    seen, result = set(), []
    for line in text.splitlines():
        line = re.sub(r'^[\d\.\-\*\s]+', '', line.strip()).strip()
        if not line or re.match(r'^(成為|這些)', line):
            continue
        for kw in (line.split(",") if "," in line else [line]):
            kw = kw.strip()
            if kw and kw not in seen:
                seen.add(kw)
                result.append(kw)
    return result


async def rag_retrieve(keywords: list[str]) -> str:
    seen_contents, sections = set(), []
    for kw in keywords:
        # asyncio.to_thread 將同步檢索丟到執行緒，避免阻塞 event loop
        docs = await asyncio.to_thread(retriever.invoke, kw)
        for d in docs:
            content = d.page_content.strip()
            if not content or content in seen_contents:
                continue
            seen_contents.add(content)
            course_name = os.path.splitext(os.path.basename(d.metadata.get("source", "未知課程.json")))[0]
            sections.append(
                f"課程名稱: {course_name}\n"
                f"教學目標: {d.metadata.get('教學目標', '')}\n"
                f"課程內容: {d.metadata.get('課程內容', content)}"
            )
    return "\n\n".join(sections)


async def recommend_courses(user_question: str) -> str:
    keyword_chain = ability_prompt | gpt_model | StrOutputParser()
    keyword_text = await keyword_chain.ainvoke({"user_question": user_question})
    keywords = extract_keywords(keyword_text)
    context = await rag_retrieve(keywords)
    rec_chain = recommend_prompt | gpt_model | StrOutputParser()
    return await rec_chain.ainvoke({"context": context, "user_question": user_question})


async def process_message(user_question: str) -> str:
    intent = await detect_intent(user_question)
    if intent == "GREETING":
        return GREETING_RESPONSE
    elif intent == "IRRELEVANT":
        return IRRELEVANT_RESPONSE
    else:
        return await recommend_courses(user_question)


# ── FastAPI 路由 ─────────────────────────────────────

@app.get("/status")
async def status():
    return {"message": "running"}


@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_text = body.decode("utf-8")

    try:
        events = parser.parse(body_text, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            reply_text = await process_message(event.message.text)

            async with AsyncApiClient(configuration) as api_client:
                line_bot_api = AsyncMessagingApi(api_client)
                await line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                    )
                )

    return "OK"


# ── 啟動（開發用）────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("course_recommend:app", host="0.0.0.0", port=8000, reload=True)