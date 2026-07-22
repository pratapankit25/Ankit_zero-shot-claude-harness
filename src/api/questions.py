import json
import queue
import threading

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api._common import ok
from domain.question import QuestionRequest
from graph.runner import run_question
from observability.events import get_logger

router = APIRouter()
log = get_logger("api.questions")

_SENTINEL = object()


@router.post("/questions")
def ask(req: QuestionRequest, request: Request) -> dict:
    detail = run_question(req.question, req.conversation_id, user=getattr(request.state, "user", None))
    return ok(detail)


@router.post("/questions/stream")
def ask_stream(req: QuestionRequest, request: Request) -> StreamingResponse:
    events: queue.Queue = queue.Queue()
    user = getattr(request.state, "user", None)

    def on_event(event: dict) -> None:
        events.put(event)

    def work() -> None:
        try:
            run_question(req.question, req.conversation_id, on_event=on_event, user=user)
        except Exception as exc:  # surfaced as SSE error, never a broken stream
            log.error("stream.run_crashed", error=str(exc))
            events.put({"type": "error", "message": f"The run crashed unexpectedly: {exc}"})
        finally:
            events.put(_SENTINEL)

    threading.Thread(target=work, daemon=True).start()

    def sse():
        while True:
            event = events.get()
            if event is _SENTINEL:
                break
            etype = event.get("type", "message")
            payload = {k: v for k, v in event.items() if k != "type"}
            yield f"event: {etype}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
