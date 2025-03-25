#!/usr/bin/python3 -W ignore


import io
import logging
import os
import urllib.parse

import opentelemetry.sdk.trace.id_generator as idg
import requests
from flask import jsonify, request
from flask_openapi3 import Info as oaInfo
from flask_openapi3 import OpenAPI, RawModel, Tag
from opentelemetry import context, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as grpcOTLPSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as httpOTLPSpanExporter,
)
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.resources import (
    SERVICE_NAME,
    SERVICE_NAMESPACE,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.trace.status import StatusCode


def get_traceid(ctx):
    for c in ctx:
        return hex(ctx[c].get_span_context().trace_id)[2:]


def get_tracecontext(custom=False):
    def create_random():
        while True:
            span_id = hex(idg.RandomIdGenerator().generate_span_id())
            if len(span_id) == 18:
                break
        return (
            f"00-{hex(idg.RandomIdGenerator().generate_trace_id())[2:]}"
            + f"-{span_id[2:]}-01"
        )

    app.logger.error(f"reqest {request.headers.get('traceparent','unset')} vs {custom}")
    if True:
        carrier = {"traceparent": request.headers.get("traceparent", create_random())}
    else:
        carrier = {"traceparent": custom}
    ctx = TraceContextTextMapPropagator().extract(carrier)
    if ctx == {}:
        ctx = context.get_current()
    app.logger.error(f"getting traceparent custom {get_traceid(ctx)}")
    return ctx


def set_tracecontext(sctx):
    def create_random():
        while True:
            span_id = hex(idg.RandomIdGenerator().generate_span_id())
            if len(span_id) == 18:
                break
        return (
            f"00-{hex(idg.RandomIdGenerator().generate_trace_id())[2:]}"
            + f"-{span_id[2:]}-01"
        )

    try:
        traceparent = f"00-{hex(sctx.trace_id)[2:]}-{hex(sctx.span_id)[2:]}-01"
        app.logger.error(f"setting traceparent {traceparent}")
    except:
        traceparent = create_random()
    return {
        "traceparent": traceparent,
        "x-b3-traceid": request.headers.get("x-b3-traceid", hex(sctx.trace_id)[2:]),
        "x-b3-spanid": request.headers.get("x-b3-spanid", hex(sctx.span_id)[2:]),
        "x-b3-parentspanid": request.headers.get(
            "x-b3-parentspanid", hex(sctx.span_id)[2:]
        ),
        "x-b3-sampled": "1",
        "x-client-trace-id": request.headers.get(
            "x-b3-traceid", hex(sctx.trace_id)[2:]
        ),
    }


VERSION = os.environ.get("VERSION", "v1.0.0")
NAMESPACE = os.environ.get("NAMESPACE", "default")
SRV_NAME = os.environ.get("OTEL_SPAN_SERVICE", os.environ.get("HOSTNAME"))

if os.environ.get("OTEL_PROTOCOL", "grpc") == "http":
    jaeger_exporter = httpOTLPSpanExporter(
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    )
elif os.environ.get("OTEL_PROTOCOL", "grpc") == "grpc":
    jaeger_exporter = grpcOTLPSpanExporter(
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        insecure=True,
    )
else:

    class NULL(io.TextIOBase):
        def write(self, text: str):
            pass

    if os.environ.get("DEBUG", False) != False:
        jaeger_exporter = ConsoleSpanExporter()
    else:
        jaeger_exporter = ConsoleSpanExporter(out=NULL())


def instrument(*args, **kwargs):
    SRV_NAME = os.environ.get("OTEL_SPAN_SERVICE", os.environ.get("HOSTNAME"))
    provider = TracerProvider(
        resource=Resource.create(
            {
                SERVICE_NAME: SRV_NAME,
                SERVICE_NAMESPACE: NAMESPACE,
                SERVICE_VERSION: VERSION,
            }
        )
    )
    if os.environ.get("OTEL_TRACE_SIMPLE", False):
        simple_processor = SimpleSpanProcessor(jaeger_exporter)
    else:
        simple_processor = BatchSpanProcessor(jaeger_exporter)
    provider.add_span_processor(simple_processor)
    trace.set_tracer_provider(provider)
    if bool(int(os.environ.get("FLASK_INSTRUMENTATION", True))):
        FlaskInstrumentor().instrument_app(
            app, tracer_provider=provider, enable_commenter=True
        )


info = oaInfo(title="OCP Alert to Trace API", version="1.0.0")
app = OpenAPI(__name__, info=info)

mocktag = Tag(name="alert-2-trace", description="Alerts to Trace")


class JsonData(RawModel):
    mimetypes = ["application/json"]


instrument()

INSTANCE = os.environ.get("INSTANCE", "production")


@app.get("/healthz", methods=["GET"])
@app.get("/health", methods=["GET"])
def healthz():
    return jsonify(dict(state="OK"))


@app.get("/readyz", methods=["GET"])
def readyz():
    return jsonify(dict(state="OK"))


@app.get("/livez", methods=["GET"])
def livez():
    return jsonify(dict(state="OK"))


@app.get("/startupz", methods=["GET"])
def startupz():
    return jsonify(dict(state="OK"))


@app.post("/webhook/alert-receiver")
def alertreceiver(raw: JsonData):
    tracer = trace.get_tracer(__name__)
    ctx = get_tracecontext(request.headers.get("traceparent", False))
    traceid = get_traceid(ctx)
    traceparent = request.headers.get("traceparent", False)
    app.logger.debug(f"Rec Headers: {request.headers}#{traceparent}")
    app.logger.info(f"/webhook/alert-receiver received request {traceid}#{traceparent}")

    def to_trace_data(data, span, traceparent):
        newdata = {}
        app.logger.debug(f"unfiltered alert data {data}#{traceparent}")
        for k in data.get("groupLabels", []):
            newdata[k] = data["groupLabels"].get(k)
        for k in data.get("commonLabels", []):
            newdata[k] = data["commonLabels"].get(k)
        for k in data.get("commonAnnotations", []):
            newdata[k] = data["commonAnnotations"].get(k)
        for k in ("receiver", "status", "externalURL", "truncatedAlerts"):
            if str(k).lower() == "externalurl":
                netloc = urllib.parse.urlparse(data.get(k)).netloc
                newdata["cluster"] = str(netloc)
            newdata[k] = data.get(k, "None")
        for alert in data.get("alerts", []):
            al = alert.get("labels")
            app.logger.debug(f"labels {al}#{traceparent}")
            span.add_event(
                al.get("alertname"),
                attributes={
                    "namespace": al.get("namespace", "None"),
                    "severity": al.get("severity", "None"),
                    "startsAt": alert.get("startsAt", "None"),
                    "endsAt": alert.get("endsAt", "None"),
                    "fingerprint": alert.get("fingerprint", "None"),
                    "cluster": newdata.get("cluster", "central"),
                },
            )
            al = alert.get("annotations")
            app.logger.debug(f"annotations {al}#{traceparent}")
            span.add_event(
                al.get("description"),
                attributes={
                    "runbook_url": al.get("runbook_url", "None"),
                    "summary": al.get("summary", "None"),
                    "startsAt": alert.get("startsAt", "None"),
                    "endsAt": alert.get("endsAt", "None"),
                    "fingerprint": alert.get("fingerprint", "None"),
                    "cluster": newdata.get("cluster", "None"),
                },
            )
        return newdata

    try:
        with tracer.start_as_current_span(
            "alert-receiver",
            context=ctx,
            attributes={SERVICE_NAMESPACE: NAMESPACE, SERVICE_VERSION: VERSION},
        ) as span:
            data = to_trace_data(request.json, span, traceparent)
            app.logger.debug(f"alert data {data}")
            span.set_attribute("app.version", VERSION)
            span.set_attribute("app.namespace", NAMESPACE)
            span.set_attribute("cluster", data.get("cluster"))
            try:
                span.add_event("alert", attributes=data)
            except Exception as alerterr:
                app.logger.error(f"cannot add data {data}#{traceparent}")
                app.logger.error(f"Exception {alerterr}#{traceparent}")
                span.set_status(StatusCode.ERROR)
                return jsonify(dict(state="error")), 200
            if data.get("status") == "resolved":
                span.set_status(StatusCode.OK)
            else:
                span.set_status(StatusCode.ERROR)
    except Exception as dataerr:
        app.logger.error(f"cannot parse data {dataerr}#{traceparent}")
    return jsonify(dict(state="ok")), 200


if __name__ == "__main__":
    app.debug = True
    app.run(
        host=os.environ.get("LISTEN", "0.0.0.0"),
        port=int(os.environ.get("PORT", 8080)),
        threaded=True,
    )
