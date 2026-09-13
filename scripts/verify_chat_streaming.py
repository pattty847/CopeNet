"""Offline desktop/mobile streaming UI check with synthetic, private-data-free output.

Run after npm run build: uv run python scripts/verify_chat_streaming.py
The real WebSocket lifecycle is covered by tests/integration/test_ws_recovery.py.
"""
import asyncio
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'src/copenet/host/frontend/dist'


async def verify(browser, width):
    context = await browser.new_context(viewport={'width': width, 'height': 900},
                                        is_mobile=width == 390, has_touch=width == 390)
    connections = []
    errors = []
    text = '## Read while the answer grows\n\n'
    seq = 1
    finished = False
    session = {'key': 'stream-check', 'sessionId': 'synthetic', 'title': 'Streaming reader check',
               'provider': 'fake', 'model': 'synthetic', 'systemPromptId': 'default',
               'taskPromptId': 'none', 'inFlightRunId': 'stream-run'}

    def answer():
        return {'role': 'assistant', 'runId': 'stream-run', 'content': text,
                'parts': [{'kind': 'text', 'content': text}],
                'state': 'final' if finished else 'delta', 'provider': 'fake', 'model': 'synthetic'}

    async def serve(route):
        url = urlparse(route.request.url)
        if url.hostname != '127.0.0.1':
            await route.abort()
            return
        target = DIST / url.path.lstrip('/')
        if not target.is_file():
            target = DIST / 'index.html'
        await route.fulfill(path=str(target), content_type=mimetypes.guess_type(target)[0] or 'application/octet-stream')

    def socket(ws):
        connections.append(ws)

        def reply(raw):
            request = json.loads(raw)
            responses = {
                'connect': {}, 'providers.list': {'providers': [{'id': 'fake', 'displayName': 'Synthetic provider', 'available': True}]},
                'sessions.list': {'sessions': [session]},
                'chat.history': {'messages': [{'role': 'user', 'runId': 'stream-run', 'content': 'Write a long answer so I can read its beginning while you continue.'}] + ([answer()] if finished else []),
                                 'activeRun': None if finished else {'runId': 'stream-run', 'seq': seq, 'message': answer()}},
                'prompts.list': {'profiles': [{'id': 'default', 'name': 'Default'}], 'taskModes': [{'id': 'none', 'name': 'Baseline'}]},
                'sessions.runs': {'runs': []}, 'tools.list': {'tools': []}, 'models.list': {'models': []},
            }
            ws.send(json.dumps({'type': 'res', 'id': request['id'], 'ok': True, 'payload': responses.get(request['method'], {})}))
        ws.on_message(reply)
        ws.send(json.dumps({'type': 'event', 'event': 'connect.challenge', 'payload': {}}))

    async def append(chunk):
        nonlocal text, seq
        text += chunk
        seq += 1
        payload = {'sessionKey': 'stream-check', 'runId': 'stream-run', 'seq': seq, 'state': 'delta',
                   'message': {**answer(), 'content': chunk}}
        for ws in list(connections):
            ws.send(json.dumps({'type': 'event', 'event': 'chat', 'payload': payload}))
        await asyncio.sleep(0.06)

    await context.route('**/*', serve)
    await context.route_web_socket('**/*', socket)
    page = await context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        await page.goto('http://127.0.0.1:17124/agents')
        viewport = page.get_by_test_id('transcript-scroll')
        await expect(page.get_by_text('Read while the answer grows', exact=True)).to_be_visible()
        for index in range(16):
            await append(f'Paragraph {index + 1}. This is synthetic verification text. The answer continues beneath the reader without moving the reading position.\n\n')
        await page.wait_for_timeout(150)
        gap = await viewport.evaluate('(el) => el.scrollHeight - el.clientHeight - el.scrollTop')
        assert gap < 5, f'Following did not reach bottom: {gap}'
        await viewport.hover()
        if width == 390:
            # Chromium touch gesture, not a synthetic scroll event.
            cdp = await context.new_cdp_session(page)
            box = await viewport.bounding_box()
            x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 3
            await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y}]})
            for offset in range(30, 301, 30):
                await cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y + offset}]})
                await page.wait_for_timeout(20)
            await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            await expect(page.get_by_role('button', name='Jump to latest')).to_be_visible()
        else:
            await page.mouse.wheel(0, -700)
            await expect(page.get_by_role('button', name='Jump to latest')).to_be_visible()
        # Read from the answer's beginning, then sample every append for jitter.
        await viewport.evaluate('(el) => { el.scrollTop = 0; }')
        await page.wait_for_timeout(250)
        top = await viewport.evaluate('(el) => el.scrollTop')
        heading = page.get_by_text('Read while the answer grows', exact=True)
        position = (await heading.bounding_box())['y']
        for index in range(12):
            await append(f'Additional paragraph {index + 1}. More output arrives while the reader stays at the beginning.\n\n')
            assert abs(await viewport.evaluate('(el) => el.scrollTop') - top) < 1
            assert abs((await heading.bounding_box())['y'] - position) < 1
        await page.screenshot(path=str(ROOT / f'docs/imgs/agents-streaming-{width}.png'))
        await page.get_by_role('button', name='Jump to latest').click()
        await append('Following has resumed.\n\n')
        assert await viewport.evaluate('(el) => el.scrollHeight - el.clientHeight - el.scrollTop') < 5
        connections.clear()
        await page.close()
        await append('Written while the browser was closed.\n\n')
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto('http://127.0.0.1:17124/agents')
        await expect(page.get_by_text('Written while the browser was closed.', exact=True)).to_be_visible()
        await append('Streaming after reopening.\n\n')
        await expect(page.get_by_text('Streaming after reopening.', exact=True)).to_be_visible()
        finished = True
        session['inFlightRunId'] = None
        connections.clear()
        await page.close()
        page = await context.new_page()
        await page.goto('http://127.0.0.1:17124/agents')
        await expect(page.get_by_text('Streaming after reopening.', exact=True)).to_be_visible()
        assert not errors, errors
        print(f'{width}px: follow, pause, stable reading, jump, close/reopen active and completed: PASS')
    finally:
        await context.close()


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            for width in (1440, 390):
                await verify(browser, width)
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
