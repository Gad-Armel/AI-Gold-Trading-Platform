# Dashboard status-fetch recovery

The supplied screenshot showed the browser refresh catch handler, not an external
calendar error. The bot worker remained active. Local HTTP checks reproduced
intermittent reset/timeout failures; their initiating transport cause was not
established. A subsequent direct HTTP read received the complete status payload.

The previous catch handler discarded the dashboard while keeping its old RUNNING
header. The replacement preserves the last successfully rendered data, clearly
marks it as cached/not live, replaces the misleading header with a connection-loss
warning, times out requests and polls serially to avoid accumulated requests.
Successful retrieval automatically clears the warning and restores current data.
HTTP errors and malformed status responses are rejected explicitly. Transient
status-file locks return retryable HTTP 503 rather than fabricated WAITING status.
Responses include Content-Length; disconnected clients are handled cleanly.
Large responses negotiate gzip with supporting clients, reducing the sampled
status response from about 78 KB to 13 KB. Explicit gzip;q=0 remains uncompressed.
Three consecutive compressed reads passed against both a temporary validation
server and the deployed main server; this does not prove all transport faults gone.

Separately, the main now requests the existing free-calendar provider directly
using an optional free_only parameter. Other callers retain their previous default
provider policy; global settings and protected Advisor 1 files were not changed.
The main's verified status reports FMP disabled and no FMP API request.

Validation: 14 targeted Python tests pass. The actual generated dashboard JavaScript
passes Node VM tests for initial rendering, failed-fetch cache retention, recovery,
HTTP 503 handling and prevention of overlapping requests. Node was available at
C:/Program Files/RStudio/resources/app/bin/node/node.exe.

Controlled demo restart found zero managed positions. Deployment stdout:
logs/monitored-main-20261020T044433Z.stdout.log. The new HTML and complete API status
were retrieved successfully; the bot reported RUNNING with fresh executable quotes.
The browser must reload the page to obtain the replacement script, preferably
Ctrl+Shift+R at http://127.0.0.1:8765/. This is dashboard resilience, not a claim that
all future network interruptions are eliminated. No trading thresholds changed.
