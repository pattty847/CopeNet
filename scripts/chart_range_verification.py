"""Offline browser assertions for the chart's time-range touch gesture."""
import asyncio
from playwright.async_api import expect


async def verify_touch_range(page, cdp, stage, y, zoomed):
    # One-finger range selection uses the same time axis without panning it.
    await page.get_by_role('button', name='Select chart region', exact=True).click()
    for step in range(9):
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart' if step == 0 else 'touchMove',
            'touchPoints': [{'id': 0, 'x': stage['x'] + stage['width'] * (.3 + step * .04), 'y': y}]})
        await asyncio.sleep(.02)
    await expect(page.locator('[data-chart-selection]')).to_be_visible()
    await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    await expect(page.locator('.ca-context')).to_contain_text('Selected range')
    await expect(page.get_by_role('button', name='Select chart drawing', exact=True)).to_have_attribute('aria-pressed', 'true')
    await page.get_by_role('button', name='Clear selected range', exact=True).click()
    assert await page.locator('.ca-context').text_content() == zoomed, 'Range selection panned the chart'
    # Leaving Range must restore native pinch zoom as well as keeping the viewport.
    x = stage['x'] + stage['width'] * .45
    for step in range(7):
        spread = 15 + step * 5
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart' if step == 0 else 'touchMove',
            'touchPoints': [{'id': 0, 'x': x - spread, 'y': y}, {'id': 1, 'x': x + spread, 'y': y}]})
        await asyncio.sleep(.04)
    await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    await asyncio.sleep(.3)
    assert await page.locator('.ca-context').text_content() != zoomed, 'Range did not restore mobile pinch zoom'
