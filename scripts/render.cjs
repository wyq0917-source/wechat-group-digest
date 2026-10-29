const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
const config=JSON.parse(fs.readFileSync(path.join(__dirname,'../runtime.local.json'),'utf8'));
const {chromium}=require(config.playwright);
(async()=>{
  const dir=path.resolve(process.argv[2]);
  const browser=await chromium.launch({executablePath:config.chromium,headless:true});
  try {
    const page=await browser.newPage({viewport:{width:960,height:900},deviceScaleFactor:2});
    await page.route('**/*',route=>route.request().url().startsWith('file:')?route.continue():route.abort());
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(pathToFileURL(path.join(dir,'index.html')).href,{waitUntil:'load'});
    await page.evaluate(()=>document.fonts.ready);
    const metrics=await page.evaluate(()=>{
      const el=document.getElementById('report');
      const end=Math.ceil(el.getBoundingClientRect().bottom+24);
      // Character ranges provide actual line boxes, so cuts do not bisect Chinese text.
      const boxes=[]; const walk=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
      while(walk.nextNode()){
        const n=walk.currentNode;if(!n.textContent.trim())continue;
        const r=document.createRange();r.selectNodeContents(n);
        for(const rect of r.getClientRects())boxes.push({top:rect.top,bottom:rect.bottom});
      }
      return {height:end,boxes,width:document.documentElement.scrollWidth};
    });
    if(metrics.width>960)throw new Error('Desktop horizontal overflow');
    const max=Number(process.env.WXREPORT_MAX_PNG_HEIGHT||7000);let y=0,part=0;const images=[];
    if(!Number.isInteger(max)||max<300||max>12000)throw new Error('PNG segment height must be 300..12000');
    while(y<metrics.height){
      const remaining=metrics.height-y;
      let end=y+Math.ceil(remaining/Math.ceil(remaining/max));
      if(end<metrics.height){
        let previous;
        do {previous=end;for(const box of metrics.boxes)if(box.top<end&&box.bottom>end)end=Math.floor(box.top-3);}while(end!==previous);
        if(end<=y)throw new Error('A report block cannot be safely split');
      }
      const name=part===0?'report.png':`report-${String(part+1).padStart(2,'0')}.png`;
      await page.setViewportSize({width:960,height:end-y});
      await page.evaluate(top=>window.scrollTo(0,top),y);
      if(await page.evaluate(()=>window.scrollY)!==y)throw new Error('Cannot position PNG segment without clipping');
      await page.screenshot({path:path.join(dir,name),animations:'disabled'});
      const png=fs.readFileSync(path.join(dir,name));
      if(png.readUInt32BE(16)!==1920||png.readUInt32BE(20)!==(end-y)*2)throw new Error('PNG dimensions do not match complete segment');
      images.push({file:name,width:1920,height:(end-y)*2,css_start:y,css_end:end});
      fs.chmodSync(path.join(dir,name),0o600);y=end;part++;
    }
    await page.setViewportSize({width:390,height:844});
    const mobile=await page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:innerWidth}));
    if(mobile.width>mobile.viewport)throw new Error('Mobile horizontal overflow');
    const first=page.locator('details').first();if(await first.count()){await first.locator('summary').click();if(!(await first.getAttribute('open')!==null))throw new Error('Cannot expand source');}
    if(errors.length)throw new Error(errors.join('\n'));
    const manifest={images,split_reason:images.length>1?'报告超过单图安全高度；在文字行之间分图，未丢弃内容。':null,desktop_width:960,mobile_width:390,offline:true,source_expansion_test:'passed',page_errors:errors};
    for(const name of fs.readdirSync(dir))if(/^report(?:-\d{2,})?\.png$/.test(name)&&!images.some(i=>i.file===name))fs.unlinkSync(path.join(dir,name));
    fs.writeFileSync(path.join(dir,'render-manifest.json'),JSON.stringify(manifest,null,2)+'\n',{mode:0o600});
    console.log(JSON.stringify(manifest));
  }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1)});
