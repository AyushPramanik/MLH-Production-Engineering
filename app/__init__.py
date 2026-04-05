import json
import logging
import os
import socket
import sys
import time

import psutil
from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, render_template

from app.database import init_db
from app.logging_config import LOG_FILE, configure_logging
from app.routes import register_routes


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def create_app():
    # Load environment from .env and allow it to override existing env vars
    load_dotenv(override=True)
    setup_logging()
    logger = logging.getLogger(__name__)

    app = Flask(__name__)

    init_db(app)

    from app import models  # noqa: F401
    from app.models.user import User
    from app.models.url import URL
    from app.models.event import Event
    from app.database import db

    try:
        opened = db.connect()
        db.create_tables([User, URL, Event], safe=True)
        if opened:
            db.close()
    except Exception:
        pass

    register_routes(app)

    # Alerting
    from app.metrics_store import store as metrics_store
    from app.alerting import AlertManager, EmailNotifier, DiscordNotifier, _now

    # @app.route("/test-alert")
    # def test_alert():
    #     mgr = getattr(app, "alert_manager", None)
    #     if mgr is None:
    #         return jsonify({"error": "alert manager not running"}), 503
    #     for notifier in mgr._notifiers:
    #         notifier.send(
    #             "[TEST] Alert Fired",
    #             "This is a test alert from your incident response system."
    #         )
    #     return jsonify({"status": "test alert sent"})
    

    if not app.config.get("TESTING"):
        db_config = {
            "host": os.environ.get("DATABASE_HOST", "localhost"),
            "port": int(os.environ.get("DATABASE_PORT", 5432)),
            "name": os.environ.get("DATABASE_NAME", "hackathon_db"),
            "user": os.environ.get("DATABASE_USER", "postgres"),
            "password": os.environ.get("DATABASE_PASSWORD", "postgres"),
        }
        alert_manager = AlertManager(
                    notifiers=[EmailNotifier(), DiscordNotifier()],
                    metrics_store=metrics_store,
                    db_config=db_config
                )
        
        alert_manager.start()
        app.alert_manager = alert_manager
        
        # -- Test routes: manual alert and intentional error trigger --
        @app.route("/test-alert")
        def test_alert():
            mgr = getattr(app, "alert_manager", None)
            if mgr is None:
                return jsonify({"error": "alert manager not running"}), 503
            for notifier in getattr(mgr, "_notifiers", []):
                try:
                    notifier.send(
                        "[TEST] Alert Fired",
                        "This is a test alert from your incident response system."
                    )
                except Exception:
                    logger.exception("test_alert_send_failed")
            return jsonify({"status": "test alert sent"})

        @app.route("/trigger-error")
        def trigger_error():
            # Intentionally raise an exception to produce a 500 and test alerting.
            raise RuntimeError("Intentional test error triggered via /trigger-error")

        @app.route("/trigger-alert-now")
        def trigger_alert_now():
            """Send an immediate test alert without raising an exception.

            This is useful when `FLASK_DEBUG` is enabled (debug mode re-raises
            exceptions and prevents the 500 errorhandler from running). The
            route returns a 500 status to simulate an error while still
            sending the alert immediately.
            """
            mgr = getattr(app, "alert_manager", None)
            if mgr is None:
                return jsonify({"error": "alert manager not running"}), 503
            try:
                body = (
                    "Intentional alert triggered via /trigger-alert-now\n\n"
                    f"Path: {request.path}\nMethod: {request.method}\nTime: {_now()}\n"
                )
                mgr._notify("[TEST] Intentional Alert", body)
            except Exception:
                logger.exception("manual_alert_failed")
            return jsonify({"status": "intentional alert sent"}), 500

    # Request logging
    @app.before_request
    def before_request():
        g.start_time = time.perf_counter()
        logger.info(f"Request started: {request.method} {request.path}")

    @app.after_request
    def after_request(response):
        start = getattr(g, "start_time", None)
        duration_ms = round((time.perf_counter() - start) * 1000, 2) if start else None
        try:
            metrics_store.record(response.status_code, duration_ms)
        except Exception:
            try:
                metrics_store.record(response.status_code)
            except Exception:
                pass
        logger.info(f"Request finished: {request.method} {request.path} status={response.status_code} duration={duration_ms}ms")
        return response

    # Routes
    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "hostname": socket.gethostname()})

    @app.route("/metrics")
    def metrics():
        mem = psutil.virtual_memory()
        process = psutil.Process(os.getpid())
        snap = metrics_store.snapshot()
        cpu = psutil.cpu_percent(interval=0.1)
        traffic_rps = round(snap["total"] / snap["window_seconds"], 2) if snap.get("window_seconds") else 0.0
        saturation = round(max(cpu, mem.percent), 2)
        return jsonify({
            "cpu_percent": cpu,
            "memory": {
                "total_mb": round(mem.total / 1024 / 1024, 2),
                "used_mb": round(mem.used / 1024 / 1024, 2),
                "available_mb": round(mem.available / 1024 / 1024, 2),
                "percent": mem.percent,
            },
            "uptime_seconds": round(time.time() - process.create_time(), 2),
            "requests": snap,
            "traffic_rps": traffic_rps,
            "latency": {
                "avg_ms": snap.get("latency_avg_ms", 0.0),
                "p95_ms": snap.get("latency_p95_ms", 0.0),
                "count": snap.get("latency_count", 0),
            },
            "saturation": saturation,
            "hostname": socket.gethostname(),
        })

    @app.route('/dashboard')
    def dashboard():
        return render_template('dashboard.html')

    @app.route("/alert-status")
    def alert_status():
        mgr = getattr(app, "alert_manager", None)
        if mgr is None:
            return jsonify({"error": "alerting not running (test mode)"}), 503
        return jsonify(mgr.status())

    @app.route("/logs")
    def logs():
        limit = request.args.get("limit", 100, type=int)
        try:
            with open(LOG_FILE) as f:
                lines = f.readlines()
            recent = lines[-limit:]
            return jsonify([json.loads(line) for line in recent if line.strip()])
        except FileNotFoundError:
            return jsonify([])

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        # Record the 500 and send an immediate alert if alert manager is running.
        try:
            try:
                metrics_store.record(500)
            except Exception:
                pass
            mgr = getattr(app, "alert_manager", None)
            if mgr is not None:
                import traceback
                tb = "".join(traceback.format_exception(type(e), e, getattr(e, "__traceback__", None)))
                body = (
                    "An unhandled exception occurred during request handling.\n\n"
                    f"Path: {request.path}\nMethod: {request.method}\nError: {e}\n\nTraceback:\n{tb}"
                )
                try:
                    mgr._notify("[ALERT] Unhandled Exception", body)
                except Exception:
                    logger.exception("failed_to_send_immediate_alert")
        except Exception:
            logger.exception("internal_error_handler_failed")
        return jsonify({"error": "internal server error"}), 500

    return app