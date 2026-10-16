/* Weekly Family Meeting local presentation layer. No telemetry, fetch, or remote assets. */
(() => {
  'use strict';
  const config = JSON.parse(document.getElementById('report-settings').textContent);
  const markdownBytes = Uint8Array.from(atob(config.markdownBase64), c => c.charCodeAt(0));
  const markdown = new TextDecoder('utf-8').decode(markdownBytes).replace(/^\uFEFF/, '');
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const renderer = new marked.Renderer();
  // Reports are data. Never execute raw Markdown HTML or active link schemes.
  renderer.html = ({text}) => escape(text);
  renderer.link = function({href, title, tokens}) {
    const text = this.parser.parseInline(tokens);
    let safe = false;
    try { safe = ['https:', 'http:'].includes(new URL(href).protocol); } catch (_) {}
    if (!safe) return text;
    return `<a href="${escape(href)}" target="_blank" rel="noopener noreferrer"${title ? ` title="${escape(title)}"` : ''}>${text}</a>`;
  };
  renderer.image = ({href, text}) => `<span class="image-reference">[图像：${escape(text || '未命名')}；${escape(href)}]</span>`;
  const holder = document.createElement('div');
  holder.innerHTML = marked.parse(markdown, {renderer, gfm:true});
  if (holder.firstElementChild?.tagName === 'H1') holder.firstElementChild.remove();
  document.getElementById('headline').textContent = config.headline;
  document.getElementById('date').textContent = config.dateLabel;
  document.getElementById('kind').textContent = config.kind;
  document.getElementById('report-id').textContent = config.reportId;
  document.getElementById('footer-version').textContent = `${config.reportId} · ${config.version}`;
  const audienceLabels={parent:['供家长阅读的分析','家长阅读'],family:['供全家共读的记录','家庭共读'],guide:['使用说明与工作规范','使用指南']};
  const labels=audienceLabels[config.audience]||audienceLabels.parent;
  document.getElementById('audience-note').textContent=labels[0];
  document.getElementById('audience-badge').textContent=labels[1];
  const toc = document.getElementById('toc');
  const chapters = document.getElementById('chapters');
  let target = document.getElementById('opening');
  let index = 0;
  for (const node of [...holder.childNodes]) {
    if (node.nodeType === 1 && node.tagName === 'H2') {
      index++;
      const label = node.textContent.replace(/^[一二三四五六七八九十]+[、.．]\s*/, '');
      target = document.createElement('section');
      target.className = 'chapter';
      if (/金句|温暖瞬间/.test(label)) target.classList.add('quotes');
      if (/镜头A|看见孩子/.test(label)) target.classList.add('analysis');
      if (/镜头B|照见父母/.test(label)) target.classList.add('reflection');
      if (/持续观察|健康信号/.test(label)) target.classList.add('signals');
      if (/父母行动|行动清单/.test(label)) target.classList.add('posture');
      if (/归档摘要/.test(label)) target.classList.add('sediment');
      if (/内容审计|审计评估/.test(label)) target.classList.add('audit');
      if (/家长阅读|阅读分界/.test(label)) target.classList.add('reader-divider');
      target.id = `section-${index}`;
      const heading = document.createElement('div');
      heading.className = 'chapter-heading';
      const number = document.createElement('span');
      number.className = 'chapter-number'; number.setAttribute('aria-hidden','true');
      number.textContent = String(index).padStart(2,'0');
      const title = document.createElement('h2'); title.textContent = label;
      heading.append(number, title); target.append(heading); chapters.append(target);
      const link = document.createElement('a'); link.href = `#${target.id}`;
      const navNumber = document.createElement('span'); navNumber.textContent = number.textContent;
      link.append(navNumber, document.createTextNode(label)); toc.append(link);
    } else target.append(node);
  }
  const introParagraphs = [...document.querySelectorAll('#opening > p')];
  if (introParagraphs.length > 1 && introParagraphs.at(-1).querySelector('strong')) {
    introParagraphs.at(-1).classList.add('reading-lead');
    introParagraphs.at(-1).dataset.label='本周的注脚';
  }
  if (introParagraphs[0]?.querySelector('br')) {
    const details=document.createElement('div');details.className='record-details';
    let line=document.createElement('span');line.className='detail-line';details.append(line);
    for(const node of [...introParagraphs[0].childNodes]){
      if(node.nodeName==='BR'){line=document.createElement('span');line.className='detail-line';details.append(line);}
      else line.append(node);
    }
    introParagraphs[0].replaceWith(details);
  }
  // Label cells for accessible stacked tables on narrow screens; source values remain intact.
  for(const table of chapters.querySelectorAll('table')){
    const labels=[...table.querySelectorAll('thead th')].map(el=>el.textContent);
    for(const row of table.querySelectorAll('tbody tr'))
      [...row.children].forEach((cell,i)=>cell.dataset.label=labels[i]||'');
  }
  // Standard Markdown headings define groups; no inference or rewritten source text.
  for (const chapter of chapters.children) {
    let subsection = chapter;
    let group = chapter;
    for (const node of [...chapter.childNodes]) {
      if (node.nodeType === 1 && node.tagName === 'H3') {
        subsection = document.createElement('section');
        subsection.className = 'subsection surface-light';
        const label = node.textContent.trim();
        if (/内容审计|事实校准|健康|风险|红旗|紧急|重要提醒|警示/.test(label)) subsection.classList.add('is-critical');
        if (/转写|边界|说明|口径|基本信息/.test(label)) subsection.classList.add('is-meta');
        chapter.insertBefore(subsection,node);
        subsection.append(node); group = subsection;
      } else if (node.nodeType === 1 && node.tagName === 'H4') {
        group = document.createElement('section'); group.className = 'topic';
        const label = node.textContent.trim();
        if (/安全|风险|红旗|校准|边界|警示|身体/.test(label)) group.classList.add('is-key');
        subsection.append(group); group.append(node);
      } else if (group !== chapter) group.append(node);
    }
  }
  const sourceLink = document.getElementById('save-markdown');
  sourceLink.href = `data:text/markdown;charset=utf-8;base64,${config.markdownBase64}`;
  sourceLink.download = config.sourceName;
  const navLinks = [...toc.querySelectorAll('a')];
  const sections = [...chapters.children];
  function updateProgress() {
    const range = document.documentElement.scrollHeight - window.innerHeight;
    document.getElementById('progress').style.width = `${range > 0 ? Math.min(100,Math.max(0,window.scrollY/range*100)) : 100}%`;
    let active = sections[0];
    for (const section of sections) if (section.getBoundingClientRect().top <= 160) active = section;
    navLinks.forEach(link => {
      const selected = link.hash === `#${active?.id}`;
      link.classList.toggle('active',selected);
      if(selected) link.setAttribute('aria-current','location'); else link.removeAttribute('aria-current');
    });
  }
  window.addEventListener('scroll', updateProgress, {passive:true}); updateProgress();
  const status = document.getElementById('export-status');
  let statusTimer;
  function notify(text, sticky=false) {
    clearTimeout(statusTimer); status.textContent = text; status.hidden=false;
    if(!sticky) statusTimer=setTimeout(()=>{status.hidden=true;},7000);
  }
  const printButton = document.getElementById('save-pdf');
  printButton.addEventListener('click', async () => {
    await document.fonts.ready;
    const title = document.title;
    document.title = config.reportId;
    notify('请在打印窗口选择“另存为 PDF”。推荐 A4、默认缩放，关闭浏览器页眉和页脚。');
    try { window.print(); } catch (error) { notify('无法打开打印窗口，请在系统浏览器打开此 HTML 后重试。'); }
    finally { document.title=title; }
  });
  const pngButton = document.getElementById('save-png');
  let previousDownloadURL;
  function download(blob,name){
    if(previousDownloadURL)URL.revokeObjectURL(previousDownloadURL);
    previousDownloadURL=URL.createObjectURL(blob);
    const link=document.createElement('a');link.href=previousDownloadURL;link.download=name;
    document.body.append(link);link.click();link.remove();
  }
  pngButton.addEventListener('click',async()=>{
    if(pngButton.disabled)return;
    pngButton.disabled=true;printButton.disabled=true;
    const originalLabel=pngButton.innerHTML;pngButton.textContent='正在生成长图…';
    notify('正在生成一张完整长图…',true);
    const stage=document.createElement('iframe');stage.className='export-stage';stage.setAttribute('aria-hidden','true');
    stage.tabIndex=-1;stage.style.width='1280px';stage.style.height='900px';stage.style.border='0';
    const markup=document.getElementById('report').cloneNode(true);
    let encoder;
    try{
      await new Promise((resolve,reject)=>{
        stage.onload=resolve;stage.onerror=()=>reject(new Error('Export viewport failed'));
        stage.srcdoc='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>'+
          document.querySelector('style').textContent+
          '.paper{width:900px!important;max-width:none;margin:0;box-shadow:none}body{margin:0;background:var(--paper)}</style></head><body>'+
          markup.outerHTML+'</body></html>';
        document.body.append(stage);
      });
      const doc=stage.contentDocument;
      await doc.fonts.ready;
      await Promise.all([...doc.images].map(img=>img.decode()));
      const clone=doc.querySelector('.paper'),width=900,scale=2;
      const height=Math.ceil(clone.getBoundingClientRect().height);
      encoder=FamilyPNG.create(width*scale,height*scale);
      // Small canvases feed consecutive rows into ONE PNG stream. No giant canvas,
      // no image splitting, no reduced quality, and no gaps at internal tile boundaries.
      const tileHeight=768;
      for(let y=0;y<height;y+=tileHeight){
        const rows=Math.min(tileHeight,height-y);
        notify('正在生成完整长图 '+Math.round(y/height*100)+'%…',true);
        const canvas=await html2canvas(clone,{scale,backgroundColor:'#fcf9f3',logging:false,
          width,height:rows,y,windowWidth:1280,windowHeight:900,scrollX:0,scrollY:0,
          allowTaint:false,useCORS:false,removeContainer:true});
        try{
          const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height);
          await encoder.addRows(pixels.data,canvas.height);
        }finally{canvas.width=0;canvas.height=0;}
      }
      notify('正在保存完整长图…',true);
      const blob=await encoder.finish();encoder=null;
      download(blob,config.reportId+'.png');
      notify('完整长图已生成，浏览器已开始保存。');
      document.dispatchEvent(new CustomEvent('family-export-complete',{detail:{format:'png',parts:1,width:width*scale,height:height*scale}}));
    }catch(error){
      console.error('PNG export failed',error);
      notify('长图生成失败，请关闭其他页面后重试，或用新版 Edge、Chrome 打开本文件。报告不会被拆分或截断。',true);
    }finally{
      if(encoder)await encoder.abort();
      stage.remove();pngButton.disabled=false;printButton.disabled=false;pngButton.innerHTML=originalLabel;
    }
  });
  document.documentElement.dataset.reportReady='true';
})();
