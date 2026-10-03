import asyncio
import pathlib
from playwright.async_api import async_playwright

async def run():
    sample_file = next(pathlib.Path('samples').glob('*CE1*.txt'))
    print('Using file:', sample_file)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        page.on('console', lambda msg: print('CONSOLE:', msg.text))
        page.on('pageerror', lambda err: print('PAGEERROR:', err))
        print('Navigating...')
        await page.goto('http://127.0.0.1:8000/#golden')
        await page.wait_for_selector('#golden-drop-zone')
        
        # Upload
        print('Uploading file...')
        file_input = await page.wait_for_selector('#golden-file-input', state='attached')
        await file_input.set_input_files(str(sample_file.resolve()))
        await page.wait_for_timeout(3000)
        
        res = await page.evaluate('''() => {
            const list = document.getElementById('golden-items-list');
            if (!list) return { error: 'no list' };
            const allGroups = list.querySelectorAll('.tree-block-group');
            const groupDetails = Array.from(allGroups).slice(0, 5).map(g => {
                const hdr = g.querySelector('.tree-block-header');
                const cnt = g.querySelector('.tree-block-content');
                return {
                    id: g.dataset.blockId,
                    groupClassName: g.className,
                    groupOffsetHeight: g.offsetHeight,
                    headerOffsetHeight: hdr ? hdr.offsetHeight : null,
                    headerComputedDisplay: hdr ? window.getComputedStyle(hdr).display : null,
                    headerComputedHeight: hdr ? window.getComputedStyle(hdr).height : null,
                    headerComputedLineHeight: hdr ? window.getComputedStyle(hdr).lineHeight : null,
                    headerText: hdr ? hdr.innerText.trim() : null,
                    headerChildren: hdr ? Array.from(hdr.children).map(c => ({
                        tag: c.tagName,
                        cls: c.className,
                        h: c.offsetHeight,
                        w: c.offsetWidth,
                        display: window.getComputedStyle(c).display,
                        text: c.innerText.slice(0, 30)
                    })) : [],
                    contentOffsetHeight: cnt ? cnt.offsetHeight : null,
                    contentClassName: cnt ? cnt.className : null
                };
            });
            
            return {
                listChildCount: list.childElementCount,
                listOffsetHeight: list.offsetHeight,
                listScrollHeight: list.scrollHeight,
                groupsCount: allGroups.length,
                groupDetails: groupDetails
            };
        }''')
        import pprint
        pprint.pprint(res)
        await page.screenshot(path='scratch/inspect_upload_screen.png', full_page=False)
        print('Screenshot saved.')
        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
