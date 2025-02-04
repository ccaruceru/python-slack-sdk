import json
import logging
import re
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler


class MockHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    default_request_version = "HTTP/1.1"
    logger = logging.getLogger(__name__)

    pattern_for_language = re.compile("python/(\\S+)", re.IGNORECASE)
    pattern_for_package_identifier = re.compile("slackclient/(\\S+)")

    error_html_response_body = '<!DOCTYPE html>\n<html lang="en">\n<head>\n\t<meta charset="utf-8">\n\t<title>Server Error | Slack</title>\n\t<meta name="author" content="Slack">\n\t<style></style>\n</head>\n<body>\n\t<nav class="top persistent">\n\t\t<a href="https://status.slack.com/" class="logo" data-qa="logo"></a>\n\t</nav>\n\t<div id="page">\n\t\t<div id="page_contents">\n\t\t\t<h1>\n\t\t\t\t<svg width="30px" height="27px" viewBox="0 0 60 54" class="warning_icon"><path d="" fill="#D94827"/></svg>\n\t\t\t\tServer Error\n\t\t\t</h1>\n\t\t\t<div class="card">\n\t\t\t\t<p>It seems like there’s a problem connecting to our servers, and we’re investigating the issue.</p>\n\t\t\t\t<p>Please <a href="https://status.slack.com/">check our Status page for updates</a>.</p>\n\t\t\t</div>\n\t\t</div>\n\t</div>\n\t<script type="text/javascript">\n\t\tif (window.desktop) {\n\t\t\tdocument.documentElement.className = \'desktop\';\n\t\t}\n\n\t\tvar FIVE_MINS = 5 * 60 * 1000;\n\t\tvar TEN_MINS = 10 * 60 * 1000;\n\n\t\tfunction randomBetween(min, max) {\n\t\t\treturn Math.floor(Math.random() * (max - (min + 1))) + min;\n\t\t}\n\n\t\twindow.setTimeout(function () {\n\t\t\twindow.location.reload(true);\n\t\t}, randomBetween(FIVE_MINS, TEN_MINS));\n\t</script>\n</body>\n</html>'

    def is_valid_user_agent(self):
        user_agent = self.headers["User-Agent"]
        return self.pattern_for_language.search(user_agent) and self.pattern_for_package_identifier.search(user_agent)

    def set_common_headers(self):
        self.send_header("content-type", "text/plain;charset=utf-8")
        self.send_header("connection", "close")
        self.end_headers()

    def do_GET(self):
        # put_nowait is common between Queue & asyncio.Queue, it does not need to be awaited
        self.server.queue.put_nowait(self.path)
        if self.path == "/received_requests.json":
            self.send_response(200)
            self.set_common_headers()
            self.wfile.write(json.dumps(self.received_requests).encode("utf-8"))
            return

    def do_POST(self):
        try:
            # put_nowait is common between Queue & asyncio.Queue, it does not need to be awaited
            self.server.queue.put_nowait(self.path)
            if self.path == "/remote_disconnected":
                # http.client.RemoteDisconnected
                self.finish()
                return

            if self.path == "/ratelimited":
                self.send_response(429)
                self.send_header("retry-after", 1)
                self.set_common_headers()
                self.wfile.write("".encode("utf-8"))
                return

            if self.path == "/timeout":
                time.sleep(2)

            # user-agent-this_is-test
            if self.path.startswith("/user-agent-"):
                elements = self.path.split("-")
                prefix, suffix = elements[2], elements[-1]
                ua: str = self.headers["User-Agent"]
                if ua.startswith(prefix) and ua.endswith(suffix):
                    self.send_response(HTTPStatus.OK)
                    self.set_common_headers()
                    self.wfile.write("ok".encode("utf-8"))
                    self.wfile.close()
                    return
                else:
                    self.send_response(HTTPStatus.BAD_REQUEST)
                    self.set_common_headers()
                    self.wfile.write("invalid user agent".encode("utf-8"))
                    self.wfile.close()
                    return

            if self.path == "/error":
                self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                # no charset here is intentional for testing
                self.send_header("content-type", "text/html")
                self.send_header("connection", "close")
                self.end_headers()
                self.wfile.write(self.error_html_response_body.encode("utf-8"))
                self.wfile.close()
                return

            body = "ok"

            self.send_response(HTTPStatus.OK)
            self.set_common_headers()
            self.wfile.write(body.encode("utf-8"))
            self.wfile.close()

        except Exception as e:
            self.logger.error(str(e), exc_info=True)
            raise
