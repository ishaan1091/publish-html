// Optional browser verification; no runtime dependencies are added to the skill.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const os = require('node:os');

(async () => {
  const html = fs.readFileSync(path.join(__dirname,'../assets/dashboard.html'),'utf8').replaceAll('{{TITLE}}','Small changes. Clearer choices.');
  const server = http.createServer((req,res)=>{res.writeHead(200,{'Content-Type':'text/html'});res.end(html);});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser = await chromium.launch({headless:true});
    const page = await browser.newPage({viewport:{width:1440,height:1080}});
    const errors=[];
    page.on('pageerror', error=>errors.push(error.message));
    page.on('console', message=>{if(message.type()==='error') errors.push(message.text());});
    page.on('requestfailed', request=>errors.push(request.url()));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    assert.equal(await page.locator('#revenue').textContent(),'$52,360');
    assert.equal(await page.locator('#rows tr').count(),4);
    await page.locator('#demand').fill('50');
    assert.equal(await page.locator('#revenue').textContent(),'$71,400');
    await page.locator('#team').selectOption('Product');
    assert.equal(await page.locator('#revenue').textContent(),'$29,400');
    assert.equal(await page.locator('#chart .bar').count(),2);
    await page.locator('#sort').selectOption('name');
    assert.equal(await page.locator('#rows tr').first().locator('td').first().textContent(),'Community');
    await page.locator('#search').fill('Direct');
    assert.equal(await page.locator('#revenue').textContent(),'$19,800');
    const downloadPromise=page.waitForEvent('download');
    await page.locator('#download').click();
    const download=await downloadPromise;
    const csv=fs.readFileSync(await download.path(),'utf8');
    assert.ok(csv.includes('"Direct","Product","13200","19800"'));
    assert.ok(!csv.includes('Community'));
    await page.locator('#search').fill('no such channel');
    assert.equal(await page.locator('#revenue').textContent(),'$0');
    assert.ok((await page.locator('#rows').textContent()).includes('No matching channels'));
    await page.locator('#reset').click();
    assert.equal(await page.locator('#revenue').textContent(),'$52,360');
    await page.locator('#demand').focus();
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#demand').inputValue(),'15');
    assert.equal(await page.locator('#revenue').textContent(),'$54,740');
    await page.locator('#reset').click();
    const screenshots=process.env.SCREENSHOT_DIR || path.join(os.tmpdir(),'publish-html-browser-results');
    fs.mkdirSync(screenshots,{recursive:true});
    await page.screenshot({path:path.join(screenshots,'desktop.png'),fullPage:true});
    for (const width of [320,390,768]) {
      await page.setViewportSize({width,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow at ${width}px`);
      assert.equal(await page.locator('#rows tr').count(),4);
    }
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(screenshots,'mobile.png'),fullPage:true});
    await page.emulateMedia({colorScheme:'dark',reducedMotion:'reduce'});
    await page.screenshot({path:path.join(screenshots,'dark.png'),fullPage:true});
    for (const kind of ['report','deck']) {
      const text=fs.readFileSync(path.join(__dirname,`../assets/${kind}.html`),'utf8').replaceAll('{{TITLE}}','A clear explanation');
      await page.emulateMedia({media:'screen',colorScheme:'light'});
      await page.setContent(text);
      if(kind==='deck') {
        assert.equal(await page.locator('.slide:visible').count(),1);
        await page.locator('#next').click();assert.equal(await page.locator('#counter').textContent(),'2 / 3');
        await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#counter').textContent(),'3 / 3');
        await page.locator('a[href="#slide-1"]').click();await page.waitForFunction(()=>document.getElementById('counter').textContent==='1 / 3');
      }else{
        await page.locator('summary').click();assert.ok(await page.locator('details').getAttribute('open')!==null);
      }
      for(const width of [320,390,768,1440]){
        await page.setViewportSize({width,height:900});
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${kind} overflow at ${width}`);
      }
      await page.emulateMedia({colorScheme:'dark',reducedMotion:'reduce'});
      await page.screenshot({path:path.join(screenshots,kind+'.png'),fullPage:true});
      await page.emulateMedia({media:'print'});
      if(kind==='deck')assert.equal(await page.locator('.slide:visible').count(),3);
    }
    // Verify the injected shell without requiring a reader's GitHub OAuth session.
    // This is deliberately a stub, not an authenticated Giscus posting test.
    const {spawnSync}=require('node:child_process');
    const fixture=spawnSync('python3',['-c',`
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import comments
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); site=root/'site'; doc=root/'doc'; site.mkdir(); doc.mkdir()
    (doc/'index.html').write_text('<!doctype html><html lang="en"><title>Public page</title><body><h1>Read without sign-in</h1></body></html>')
    (site/'.publish-html.json').write_text(json.dumps({'comments':{'enabled':True,'provider':'giscus','repo':'reader/reports','repo_id':'R_demo','category_id':'DIC_demo','category':'Feedback'}}))
    comments.decorate(doc,site,'reader/reports','stable')
    print((doc/'index.html').read_text())
`,path.join(__dirname,'../scripts')],{encoding:'utf8'});
    assert.equal(fixture.status,0,fixture.stderr);
    await page.route('https://giscus.app/client.js',route=>route.fulfill({contentType:'application/javascript',body:'window.commentShellLoaded=true;'}));
    await page.emulateMedia({media:'screen'});
    await page.setContent(fixture.stdout);
    await page.waitForFunction(()=>window.commentShellLoaded===true);
    assert.equal(await page.locator('h1').textContent(),'Read without sign-in');
    assert.equal(await page.locator('script[data-term]').getAttribute('data-term'),'publish-html:stable');
    assert.equal(await page.locator('script[data-term]').count(),1);
    assert.ok(await page.getByRole('link',{name:'View discussions on GitHub'}).isVisible());
    assert.deepEqual(errors,[]);
    console.log('PASS: calculations, combined filtering, sorting, search/empty state, CSV export, reset, keyboard slider, responsive widths, no JS errors.');
    console.log('PASS: optional comment shell remains publicly readable (Giscus client stubbed; OAuth posting not tested).');
    console.log('Screenshots: '+screenshots);
  } finally {
    if(browser) await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
