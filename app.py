#!/usr/bin/python
import asyncio
import json
import logging
import os

import aiohttp
from aiohttp import client, web
from multidict import MultiDict, MultiDictProxy

from a2t.tracing import *

logging.basicConfig()
logger = logging.getLogger(__name__)
if int(os.environ.get("DEBUG", False)) is True:
    logger.setLevel(logging.DEBUG)

instrument()
tracer = trace.get_tracer("alerts-to-traces")


def flatten_struct(headers):
    newheaders = {}
    for h in headers:
        if isinstance(headers[h], dict):
            newheaders.update(dict(flatten_struct(headers[h])))
            continue
        newheaders[h] = headers[h]
    return newheaders


def get_source(headers):
    return headers.get("x-forwarded-for", "").split(",")[0]


def get_traceparent(_ctx):
    logger.error(f"debug get_traceparent {_ctx}")
    try:
        traceparent = f"00-{hex(_ctx.trace_id)[2:]}-{hex(_ctx.span_id)[2:]}-01"
    except Exception as perr:
        try:
            if isinstance(_ctx, Context):
                cspan = _ctx.get(list(_ctx.keys())[0]).get_span_context()
                traceparent = (
                    f"00-{hex(cspan.trace_id)[2:]}-{hex(cspan.span_id)[2:]}-01"
                )
        except Exception as perr:
            traceparent = ""
    logger.error(f"found traceparent {traceparent}")
    return traceparent


@web.middleware
async def opentelemetry(request, handler):
    tracer = trace.get_tracer("aiohttp.server")
    with tracer.start_as_current_span(
        "aiohttp.handler", kind=trace.SpanKind.SERVER
    ) as span:
        return await handler(request)


async def health(req):
    return web.Response(status=200, body="OK")


async def handler_alert_receiver(req):
    status = 200
    headers = req.headers.copy()
    _ctx = get_tracecontext(headers=dict(headers))
    try:
        with tracer.start_as_current_span(
            "downstream request",
            attributes=dict(headers),
        ) as span:
            try:
                data = await req.json()
            except:
                data = await req.read()
                logger.error(
                    f"didn't receive json from downstream only body {body}",
                    extra={"traceparent": get_traceparent(_ctx)},
                )
            try:
                with tracer.start_as_current_span(
                    "alert-receiver",
                    attributes={
                        "status": data.get("status"),
                        "count": len(data.get("alerts", [])),
                        "origin": get_source(headers),
                    },
                ) as aspan:
                    logger.debug(
                        f"data for trace {dict(data)}",
                        extra={"traceparent": get_traceparent(_ctx)},
                    )
                    for alert in data.get("alerts", []):
                        aspan.add_event("alert", attributes=dict(flatten_struct(alert)))
                        if data.get("status") == "resolved":
                            aspan.set_status(StatusCode.OK)
                        else:
                            aspan.set_status(StatusCode.ERROR)
                    logger.info(
                        f"received {len(data.get('alerts',[]))} from {get_source(headers)}",
                        extra={"traceparent": get_traceparent(_ctx)},
                    )
                span.set_attribute("cluster", alert.get("region", "local"))
                span.set_status(StatusCode.OK)
            except Exception as alterr:
                logger.error(
                    f"Exception handling alert to trace {alterr}",
                    extra={"traceparent": get_traceparent(_ctx)},
                )
                span.record_exception(alterr)
                span.set_status(StatusCode.ERROR)

            return web.Response(
                status=201,
                headers={"traceparent": get_traceparent(_ctx)},
            )
    except Exception as perr:
        logger.error(
            f"Exception handling alert to trace {perr}",
            extra={"traceparent": get_traceparent(_ctx)},
        )
        return web.Response(
            status=503, body=str(perr), headers={"traceparent": get_traceparent(_ctx)}
        )


async def app_factory():
    app = web.Application(middlewares=[opentelemetry])
    app.router.add_route("*", "/health", health)
    app.router.add_route("*", "/webhook/alert-receiver", handler_alert_receiver)
    return app


if __name__ == "__main__":
    web.run_app(app_factory(), port=int(os.environ.get("PORT", 8080)))
