from utils.warning_filters import suppress_known_third_party_warnings

suppress_known_third_party_warnings()

import threading
import time
import os
import socket
import phoenix as px
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from utils.logger import logger

_PHOENIX_LAUNCHED = False
_PHOENIX_STARTING = False
_PHOENIX_LOCK = threading.Lock()
_PHOENIX_THREAD = None
_TRACER_PROVIDER = None
_SPAN_PROCESSOR = None

def _can_bind_ipv6(address: str, port: int) -> bool:
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((address, port))
        s.close()
        return True
    except OSError:
        return False

def _find_available_ipv6_port() -> int:
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.bind(("::1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def launch_phoenix_monitor(port=6006):
    """
    Launch Arize Phoenix in a background thread and instrument LangChain.
    """
    global _PHOENIX_LAUNCHED, _PHOENIX_STARTING, _PHOENIX_THREAD, _TRACER_PROVIDER, _SPAN_PROCESSOR

    try:
        # 使用 Phoenix 默认工作目录，避免在项目根目录生成监控数据目录
        os.environ["PHOENIX_PORT"] = str(port)
        os.environ["PHOENIX_HOST"] = "127.0.0.1"
        if not _can_bind_ipv6("::1", 0):
            logger.warning("检测到系统 IPv6 不可用，跳过 Phoenix 启动。")
            return
        grpc_port = int(os.getenv("PHOENIX_GRPC_PORT", "4317"))
        if not _can_bind_ipv6("::", grpc_port):
            grpc_port = _find_available_ipv6_port()
        os.environ["PHOENIX_GRPC_PORT"] = str(grpc_port)

        with _PHOENIX_LOCK:
            if _PHOENIX_LAUNCHED or _PHOENIX_STARTING:
                return
            _PHOENIX_STARTING = True

        def _launch():
            global _PHOENIX_LAUNCHED, _PHOENIX_STARTING, _TRACER_PROVIDER, _SPAN_PROCESSOR
            try:
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        px.launch_app()
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise e
                        logger.warning(f"Phoenix launch attempt {attempt+1} failed: {e}. Retrying in 2s...")
                        time.sleep(2)

                tracer_provider = TracerProvider()
                trace.set_tracer_provider(tracer_provider)
                
                phoenix_otlp_endpoint = f"http://localhost:{port}/v1/traces"
                span_processor = SimpleSpanProcessor(OTLPSpanExporter(endpoint=phoenix_otlp_endpoint))
                tracer_provider.add_span_processor(span_processor)
                try:
                    from openinference.instrumentation.langchain import LangChainInstrumentor
                    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
                except ImportError:
                    logger.warning("LangChainInstrumentor not found, skipping auto-instrumentation.")
                with _PHOENIX_LOCK:
                    _TRACER_PROVIDER = tracer_provider
                    _SPAN_PROCESSOR = span_processor
                    _PHOENIX_LAUNCHED = True
                    _PHOENIX_STARTING = False
                
                logger.info(f"🚀 Phoenix Observability launched at: http://localhost:{port}")
                logger.info(f"📡 OTLP Exporter connected to: {phoenix_otlp_endpoint}")
            except Exception as e:
                with _PHOENIX_LOCK:
                    _PHOENIX_STARTING = False
                    _PHOENIX_LAUNCHED = False
                logger.error(f"Phoenix Launch Error: {e}")

        _PHOENIX_THREAD = threading.Thread(target=_launch, daemon=True)
        _PHOENIX_THREAD.start()
        
    except Exception as e:
        with _PHOENIX_LOCK:
            _PHOENIX_STARTING = False
        logger.error(f"❌ Failed to launch Phoenix: {e}")
        logger.warning("⚠️  Proceeding without observability.")

def shutdown_phoenix_monitor():
    global _PHOENIX_LAUNCHED, _PHOENIX_STARTING, _TRACER_PROVIDER, _SPAN_PROCESSOR
    with _PHOENIX_LOCK:
        if _SPAN_PROCESSOR is not None:
            try:
                _SPAN_PROCESSOR.force_flush()
            except Exception:
                pass
        if _TRACER_PROVIDER is not None:
            try:
                _TRACER_PROVIDER.shutdown()
            except Exception:
                pass
        _TRACER_PROVIDER = None
        _SPAN_PROCESSOR = None
        _PHOENIX_LAUNCHED = False
        _PHOENIX_STARTING = False

if __name__ == "__main__":
    launch_phoenix_monitor()
    while True:
        time.sleep(1)
