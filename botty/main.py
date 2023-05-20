
import os
import asyncio
import uuid
import json
import traceback
import sys

from pydantic import BaseModel

from enum import Enum

from typing import Any, AsyncIterable, Dict, Optional, Union

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse,FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi_poe import make_app
from fastapi_poe.types import (
    ContentType,
    QueryRequest,
    ReportErrorRequest,
    ReportFeedbackRequest,
    SettingsRequest,
    SettingsResponse,
)

import socketio as SocketIO

import colorama

from pygments import highlight
from pygments.lexers import JsonLexer
from pygments.formatters import TerminalFormatter

import openai



colorama.init(autoreset=True)


sio = SocketIO.AsyncServer(async_mode='asgi')
app = FastAPI()


# MAKE SURE YOU CALL sapp FROM UVICORN NOT app
sapp = SocketIO.ASGIApp(sio, app)

app.mount("/static", StaticFiles(directory="static"))
app.mount("/static/js", StaticFiles(directory="static/js"))
app.mount("/static/css", StaticFiles(directory="static/css"))


def logAttention(data):
    print(colorama.Fore.LIGHTCYAN_EX + data + colorama.Style.RESET_ALL)

def logInput(data):
    print(colorama.Fore.LIGHTGREEN_EX + data + colorama.Style.RESET_ALL)

def logInfo(data):
    print(colorama.Fore.CYAN + data + colorama.Style.RESET_ALL)

def logWarn(data):
    print(colorama.Fore.YELLOW + data + colorama.Style.RESET_ALL)

def logError(data):
    #tb = traceback.format_exc()
    #print(colorama.Fore.RED + f"ERROR: {tb}" + colorama.Style.RESET_ALL)
    print(colorama.Fore.RED + f"ERROR: {data}" + colorama.Style.RESET_ALL)

def serialize_data(data: Any) -> Any:
    try:
        if isinstance(data, list):
            return [serialize_data(item) for item in data]
        elif isinstance(data, dict):
            return {key: serialize_data(value) for key, value in data.items()}
        elif isinstance(data, BaseModel):
            return data.dict()
        elif isinstance(data, Enum):
            return data.value
        else:
            return data
    except TypeError as e:
        logError(f"Error while serializing: {data} of type {type(data)}")
        raise e

def to_json(data: Any) -> str:
    return json.dumps(serialize_data(data), indent=4)

def logJson(data):
    json_str = to_json(data)
    colored_json = highlight(json_str, JsonLexer(), TerminalFormatter())
    print(colored_json)



call_map = {}


@sio.on('remote_reply')
def reply_handler(conn, buffer):
    #print("buffer:" + buffer)
    try:
        reply = json.loads(buffer)

        logInfo("Received reply")
        #logJson(reply)

        f = call_map.get(reply['handle'])
        if f:
            if reply.get('error'):
                f(None, reply['error'])
            else:
                f(reply['data'], None)

            del call_map[reply['handle']]
        else:
            logError(f"Reply is using an invalid or stale handle: {reply['handle']}")

    except Exception as err:
        logError(f"reply failed: {err}")


def make_remote_request(client_handle: str):
    future = asyncio.Future()

    def handle_remote_reply(data, error_msg):

        if error_msg:
            # this is a command error not a connection error
            future.set_exception(Exception(error_msg))
        else:
            send_input(data)
            future.set_result(data)


    call_map[client_handle] = handle_remote_reply
    return future



def send_request(command:str, data=None):
    logInfo(f"Sending remote request: {command}")

    handle = str(uuid.uuid4())

    p = make_remote_request(handle)

    msg = {
        'command': command,
        'data': data,
        'handle': handle
    }

    asyncio.create_task(sio.emit('remote_request', json.dumps(msg)))

    return p




def send_warn(msg):
    logWarn(msg)
    asyncio.create_task(sio.emit('warn', msg))

def send_error(msg):
    logError(msg)
    asyncio.create_task(sio.emit('error', msg))

def send_info(msg):
    logInfo(msg)
    asyncio.create_task(sio.emit('message', msg))

def send_attention(msg):
    logAttention(msg)
    asyncio.create_task(sio.emit('attention', msg))

def send_input(msg):
    if (msg):
        logInput(msg)
        asyncio.create_task(sio.emit('input', msg))



@sio.on('message')
async def handle_message(conn, message):
    logInfo('Received message: ' + message)
    if (message is None):
        message = ""
    else:
        send_input(message)

        newItem = [{
            'role': "user",
            'content': message
        }]
        response = await send_llm(newItem, 50)
        logInfo("Got LLM response: " + response)
        send_info(response)
        #yield self.text_event(response)

@app.get("/")
async def index():
    print("Getting index")
    return FileResponse("static/index.html")

@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/favicon.ico")










http_bearer = HTTPBearer()

def find_auth_key(api_key: str, *, allow_without_key: bool = False) -> Optional[str]:
    if not api_key:
        if os.environ.get("POE_API_KEY"):
            logInfo("Found Poe API key")
            api_key = os.environ["POE_API_KEY"]
        else:
            if allow_without_key:
                return None
            logError(
                "Please provide a Poe API key. You can get a key from the create_bot form at:"
            )
            logError("https://poe.com/create_bot?api=1")
            logError(
                "You can pass the API key to the run() function or "
                "use the POE_API_KEY environment variable."
            )
            sys.exit(1)
    if len(api_key) != 32:
        logError("Invalid Poe API key (should be 32 characters)")
        sys.exit(1)
    return api_key

auth_key = find_auth_key("", allow_without_key=False)

def auth_user(
    authorization: HTTPAuthorizationCredentials = Depends(http_bearer),
) -> None:
    if auth_key is None:
        return
    if authorization.scheme != "Bearer" or authorization.credentials != auth_key:
        logError("Bot authorization failed - check key: " + auth_key)
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

class PoeBot:
    # Override these for your bot

    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        """Override this to return a response to user queries."""
        chatlog = query.query
        logJson(chatlog)
        logInfo("Sending to LLM")
        flat_chatlog = []
        for item in chatlog:
            newRole = item.role

            if newRole == "bot":
                newRole = "assistant"

            newItem = {
                'role': newRole,
                'content': item.content
            }

            flat_chatlog.append(newItem)

        logJson(flat_chatlog)

        response = await send_llm(flat_chatlog, 50)
        logInfo("Got LLM response: " + response)
        yield self.text_event(response)

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        """Override this to return non-standard settings."""
        return SettingsResponse()

    async def on_feedback(self, feedback_request: ReportFeedbackRequest) -> None:
        """Override this to record feedback from the user."""
        pass

    async def on_error(self, error_request: ReportErrorRequest) -> None:
        """Override this to record errors from the Poe server."""
        send_error("Got Poe error")
        logJson(error_request)

    # Helpers for generating responses

    @staticmethod
    def text_event(text: str) -> ServerSentEvent:
        return ServerSentEvent(data=json.dumps({"text": text}), event="text")

    @staticmethod
    def replace_response_event(text: str) -> ServerSentEvent:
        return ServerSentEvent(
            data=json.dumps({"text": text}), event="replace_response"
        )

    @staticmethod
    def done_event() -> ServerSentEvent:
        return ServerSentEvent(data="{}", event="done")

    @staticmethod
    def suggested_reply_event(text: str) -> ServerSentEvent:
        return ServerSentEvent(data=json.dumps({"text": text}), event="suggested_reply")

    @staticmethod
    def meta_event(
        *,
        content_type: ContentType = "text/markdown",
        refetch_settings: bool = False,
        linkify: bool = True,
        suggested_replies: bool = True,
    ) -> ServerSentEvent:
        return ServerSentEvent(
            data=json.dumps(
                {
                    "content_type": content_type,
                    "refetch_settings": refetch_settings,
                    "linkify": linkify,
                    "suggested_replies": suggested_replies,
                }
            ),
            event="meta",
        )

    @staticmethod
    def error_event(
        text: Optional[str] = None, *, allow_retry: bool = True
    ) -> ServerSentEvent:
        data: Dict[str, Union[bool, str]] = {"allow_retry": allow_retry}
        if text is not None:
            data["text"] = text
        return ServerSentEvent(data=json.dumps(data), event="error")

    # Internal handlers

    async def handle_report_feedback(
        self, feedback_request: ReportFeedbackRequest
    ) -> JSONResponse:
        await self.on_feedback(feedback_request)
        return JSONResponse({})

    async def handle_report_error(
        self, error_request: ReportErrorRequest
    ) -> JSONResponse:
        await self.on_error(error_request)
        return JSONResponse({})

    async def handle_settings(self, settings_request: SettingsRequest) -> JSONResponse:
        settings = await self.get_settings(settings_request)
        return JSONResponse(settings.dict())

    async def handle_query(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        try:
            async for event in self.get_response(query):
                yield event
        except Exception as e:
            send_error(str(e))
            yield self.error_event(repr(e), allow_retry=False)
        yield self.done_event()

bot = PoeBot()


@app.post("/")
async def poe_post(request: Dict[str, Any], dict=Depends(auth_user)):
    send_attention("Got Poe [" + request["type"] + "] request")
    #logJson(request)
    if request["type"] == "query":
        qo = QueryRequest.parse_obj(request)
        #logJson(qo.dict())
        return EventSourceResponse(
            bot.handle_query(qo)
        )
    elif request["type"] == "settings":
        return await bot.handle_settings(SettingsRequest.parse_obj(request))
    elif request["type"] == "report_feedback":
        return await bot.handle_report_feedback(
            ReportFeedbackRequest.parse_obj(request)
        )
    elif request["type"] == "report_error":
        return await bot.handle_report_error(ReportErrorRequest.parse_obj(request))
    else:
        raise HTTPException(status_code=501, detail="Unsupported request type")












@sio.on('connect')
def handle_connect(conn, message, data):
    send_attention("Connected")
    asyncio.create_task(init_bot())


print(colorama.Fore.LIGHTMAGENTA_EX + "Starting server" + colorama.Style.RESET_ALL)




configFilepath = "memory/config.json"

async def assert_config():

    if os.path.exists(configFilepath):
        send_warn('I found an existing memory config')

        with open(configFilepath, "r") as infile:
            config = json.loads(infile.read())
        logJson(config)

    else:
        send_error('No memory config found! Running first time setup...')

        config = {
            "OPENAI_API_KEY": "dummy"
        }

        await save_config(config)

    return config

async def save_config(config):
    os.makedirs(os.path.dirname(configFilepath), exist_ok=True)
    with open(configFilepath, "w") as outfile:
        json.dump(config, outfile)

async def do_config():

    config = await assert_config()

    success = False
    while not success:

        try:
            await validate_openai(config)
            success = True
        except Exception as e2:
            if config.get("OPENAI_API_KEY") != "dummy":
                send_error(f"{e2}")

            apiKey = await send_request('Please enter your OpenAI API key below')
            print(colorama.Fore.YELLOW + "Got API key " + apiKey + colorama.Style.RESET_ALL)

            config["OPENAI_API_KEY"] = apiKey
            await save_config(config)

    send_attention('Success!')

    if config.get("name"):
        logInfo("Bot name found")
    else:
        logError("No bot name found")
        name = await send_request("Your bot needs a first name. Please provide it below")
        config["name"] = name
        await save_config(config)
    send_attention("Bot name: " + config["name"])
    await sio.emit('title', config["name"])
    return config


connected = False
async def validate_openai(config):
    global connected
    if connected:
        send_info("Already connected to OpenAI...")
        return

    #verify the api key works
    send_attention("Connecting to OpenAI...")

    openai.api_key = config.get("OPENAI_API_KEY")
    #engines = openai.Engine.list()
    #logJson(engines)
    # this is a test to see if things are actually working
    response = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            #model='gpt-4',
            messages=[
                {
                    "role": "system",
                    "content": "pretend you are half sleep"
                },
                {
                    "role": "user",
                    "content": "i'm finna go sleep"
                }
            ],
            temperature=0,
            max_tokens=300
    )
    logJson(response)
    connected = True





#response = await send_bot("pretend your name is " + config["name"] + " and then greet the user in a calm, neutral tone","hello",10)
async def send_llm(messages, maxTokens=100):
    response = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            #model='gpt-4',
            messages=messages,
            temperature=0,
            max_tokens=maxTokens
    )
    logJson(response)
    botspeak = response["choices"][0]["message"]["content"]
    return botspeak



async def init_bot():
    try:
        config = await do_config()
        logInfo("Loading config")
        #memory = await do_memory()

    except Exception as e:
        send_error(f"{e}")
