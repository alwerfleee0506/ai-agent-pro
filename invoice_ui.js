// Invoice arithmetic uses integer decimal units, never Number/parseFloat rounding.
const InvoiceMath=(()=>{
 const limit=1000000000000000000n;
 function parse(value){
  if(value==null||String(value).trim()==='')return null;
  if(typeof value==='boolean')throw Error('قيمة غير صالحة');
  let s=String(value).trim().replace(/[٠-٩]/g,c=>String(c.charCodeAt(0)-1632)).replace(/[۰-۹]/g,c=>String(c.charCodeAt(0)-1776)).replace(/٫/g,'.');
  if(s.includes('٬')){if(!/^\d{1,3}(?:٬\d{3})+(?:\.\d{1,6})?$/.test(s))throw Error('راجع فواصل الآلاف');s=s.replace(/٬/g,'')}
  if(/^\d{1,3}(?:[ \u00a0]\d{3})+(?:\.\d{1,6})?$/.test(s))s=s.replace(/[ \u00a0]/g,'');
  if(s.includes(',')){if(/^\d{1,3}(?:,\d{3}){2,}(?:\.\d{1,6})?$/.test(s)||/^\d{1,3}(?:,\d{3})+\.\d{1,6}$/.test(s))s=s.replace(/,/g,'');else if(/^\d+,\d{1,2}$/.test(s))s=s.replace(',','.');else throw Error('الفاصلة ملتبسة؛ استعمل نقطة للعشرية أو احذف فاصل الآلاف')}
  if(s.length>32||!/^\d+(?:\.\d{1,6})?$/.test(s))throw Error('رقم موجب أو صفر، حتى 6 منازل عشرية');
  const [whole,fraction='']=s.split('.');if((whole+fraction).replace(/^0+/,'').replace(/0+$/,'').length>15)throw Error('الرقم يتجاوز دقة Excel');
  const n=BigInt(whole)*1000000n+BigInt(fraction.padEnd(6,'0'));if(n>limit)throw Error('الرقم أكبر من الحد المسموح');return n;
 }
 function round(n,d){const sign=n<0n?-1n:1n;const v=n*sign;return sign*((v+d/2n)/d)}
 function fmt(n){if(n==null)return 'غير مكتمل';const sign=n<0n?'-':'';let s=(n<0n?-n:n).toString().padStart(4,'0');return sign+s.slice(0,-3)+'.'+s.slice(-3)}
 function row(item){const issues=[];let q=null,p=null,t=null;for(const [key,label] of [['quantity','الكمية'],['unit_price','السعر'],['line_total','الإجمالي المطبوع']]){try{const n=parse(item[key]);if(key==='quantity')q=n;if(key==='unit_price')p=n;if(key==='line_total')t=n;if(n==null&&key!=='line_total')issues.push(label+' ناقص')}catch(e){issues.push(label+': '+e.message)}}if(!String(item.name||'').trim())issues.push('اسم الصنف ناقص');const amount=q==null||p==null?null:round(q*p,1000000000n);if(amount!=null&&amount>1000000000000000n)issues.push('إجمالي السطر أكبر من الحد');const diff=amount==null||t==null?null:round(amount*1000n-t,1000n);return {amount,diff,issues}}
 return {parse,round,fmt,row};
})();
let invoiceOriginalDocument=null,invoiceSourceURL=null,invoiceRevision=0;
function invoiceInvalidate(){invoiceRevision++;$('invoiceConfirmed').checked=false;$('invoiceDownload').replaceChildren()}
function currentInvoice(){return {...invoiceState,supplier:$('invSupplier').value,invoice_number:$('invNumber').value,date:$('invDate').value,currency:$('invCurrency').value,printed_total:$('invTotal').value||null,discount:$('invDiscount').value||null,tax:$('invTax').value||null,charges:$('invCharges').value||null,total_review_note:$('invTotalNote').value,total_reviewed:$('invTotalReviewed').checked}}
function invoiceTotals(){
 if(!invoiceState)return;
 let subtotal=0n,complete=true,flagged=0;const errors=[];
 invoiceState.items.forEach(item=>{const r=InvoiceMath.row(item);if(r.amount==null||r.issues.length)complete=false;else subtotal+=r.amount;if(r.issues.length||r.diff!=null&&r.diff!==0n||item.uncertain_fields?.length)flagged++});
 let discount=0n,tax=0n,charges=0n,printed=null;
 for(const [id,key] of [['invDiscount','discount'],['invTax','tax'],['invCharges','charges'],['invTotal','printed']]){try{const n=InvoiceMath.parse($(id).value);if(key==='discount')discount=InvoiceMath.round(n||0n,1000n);if(key==='tax')tax=InvoiceMath.round(n||0n,1000n);if(key==='charges')charges=InvoiceMath.round(n||0n,1000n);if(key==='printed')printed=n}catch(e){errors.push(e.message);complete=false}}
 const total=complete?subtotal-discount+tax+charges:null,difference=total==null||printed==null?null:InvoiceMath.round(total*1000n-printed,1000n);
 const summary=$('invoiceSummary');summary.replaceChildren();for(const [label,value] of [['الأصناف',String(invoiceState.items.length)],['المجموع المحسوب',InvoiceMath.fmt(total)],['فرق الإجمالي',difference==null?'لا تتوفر مقارنة':InvoiceMath.fmt(difference)],['سطور للمراجعة',String(flagged)]]){const card=textNode('div','','invoice-metric');card.append(textNode('small',label),textNode('strong',value));summary.append(card)}
 const mismatch=difference!=null&&difference!==0n;$('invTotalReview').hidden=!mismatch;
 if(total!=null&&(total<0n||total>1000000000000000n))errors.push('راجع الإجمالي ومبالغ الخصم والضريبة والرسوم.');
 $('invoiceLiveErrors').replaceChildren(...errors.map(e=>textNode('small',e)));
 return {complete:complete&&!errors.length,difference};
}
async function invoiceDocument(file){return {name:file.name,data:await encodeFile(file)}}
$('invoiceFile').addEventListener('change',()=>{if(busy)return;invoiceState=null;invoiceOriginalDocument=null;invoiceInvalidate();$('invoiceReview').hidden=true;$('invoiceQuality').textContent='';$('invoiceSource').replaceChildren();if(invoiceSourceURL)URL.revokeObjectURL(invoiceSourceURL);invoiceSourceURL=null});
$('scanInvoice').addEventListener('click',async()=>{
 if(busy||active)return;const file=$('invoiceFile').files[0];if(!file){status.textContent='اختار صورة فاتورة أو PDF أولاً.';return}if(file.size>6*1024*1024){status.textContent='الحد 6 MB لكل فاتورة.';return}
 busy=true;update();$('scanInvoice').disabled=$('invoiceFile').disabled=$('invoiceVerify').disabled=true;$('invoiceReading').hidden=false;status.textContent=$('invoiceVerify').checked?'نقرأ الأصل ثم نقارن قراءة مستقلة ثانية…':'نقرأ الفاتورة من الأصل…';
 try{
  const document=await invoiceDocument(file),data=await featureAPI('/invoice/scan',{method:'POST',body:JSON.stringify({document,verify:$('invoiceVerify').checked})});invoiceState=data.invoice;invoiceOriginalDocument=document;$('invoiceIncludeSource').disabled=false;$('invoiceIncludeSource').checked=true;invoiceInvalidate();
  for(const [id,key] of [['invSupplier','supplier'],['invNumber','invoice_number'],['invDate','date'],['invCurrency','currency'],['invTotal','printed_total'],['invDiscount','discount'],['invTax','tax'],['invCharges','charges']])$(id).value=invoiceState[key]??(invoiceState.metadata_uncertain?.includes(key)?invoiceState.raw_metadata?.[key]:'')??'';
  $('invTotalNote').value='';$('invTotalReviewed').checked=false;
  const labels={agreed:'قراءتان متطابقتان — راجع الأصل قبل الاعتماد',disagreed:'يوجد اختلاف بين القراءتين — السطور المعنية مميزة',unavailable:'لم تكتمل القراءة الثانية — راجع القراءة الأولى',not_requested:'قراءة واحدة — راجع الأسماء والأرقام'};
  $('invoiceQuality').textContent=labels[invoiceState.verification?.status]||labels.not_requested;
  if(invoiceSourceURL)URL.revokeObjectURL(invoiceSourceURL);invoiceSourceURL=URL.createObjectURL(file);const source=$('invoiceSource');source.replaceChildren();const link=textNode('a','فتح أصل الفاتورة بالحجم الكامل');link.href=invoiceSourceURL;link.target='_blank';link.rel='noopener';source.append(link);if(file.type.startsWith('image/')){const image=new Image();image.src=invoiceSourceURL;image.alt='أصل الفاتورة للمقارنة';source.append(image)}else source.append(textNode('small','افتح PDF من الرابط لمقارنة الصفحات.'));
  renderInvoice();$('invoiceReview').hidden=false;status.textContent=data.notice;
 }catch(error){featureError(error)}finally{busy=false;$('scanInvoice').disabled=$('invoiceFile').disabled=$('invoiceVerify').disabled=false;$('invoiceReading').hidden=true;update()}
});
function renderInvoice(){
 invoiceInvalidate();const body=$('invoiceTable').tBodies[0];body.replaceChildren();
 invoiceState.items.forEach((item,index)=>{
  const row=document.createElement('tr');const inputs={};
  for(const [key,label] of [['name','اسم الصنف'],['quantity','الكمية'],['unit_price','سعر الوحدة'],['line_total','الإجمالي المطبوع']]){const td=document.createElement('td'),input=document.createElement('input');td.dataset.label=label;input.dir=key==='name'?'auto':'ltr';input.value=item[key]??item['raw_'+key]??'';input.setAttribute('aria-label',label+'، السطر '+(index+1));input.maxLength=key==='name'?300:32;if(key!=='name')input.inputMode='decimal';inputs[key]=input;td.append(input);row.append(td)}
  const calculated=textNode('td',''),diff=textNode('td',''),review=document.createElement('td');calculated.dataset.label='الإجمالي المحسوب';diff.dataset.label='فرق السطر';calculated.dir=diff.dir='ltr';review.className='invoice-row-review';const hint=textNode('small','');const label=textNode('label','راجعت السطر أمام الأصل ');const check=document.createElement('input');check.type='checkbox';check.checked=item.reviewed===true;label.append(check);const note=document.createElement('input');note.placeholder='توضيح الفرق إن وُجد';note.maxLength=300;note.value=item.review_note||'';review.append(hint,label,note);row.append(calculated,diff,review);
  function refresh(){const r=InvoiceMath.row(item);item.calculated_total=r.amount==null?null:InvoiceMath.fmt(r.amount);item.difference=r.diff==null?null:InvoiceMath.fmt(r.diff);calculated.textContent=item.calculated_total??'غير مكتمل';diff.textContent=r.diff==null?'غير متوفر':InvoiceMath.fmt(r.diff);const ambiguous=item.uncertain_fields||[],needs=r.issues.length||r.diff!=null&&r.diff!==0n||ambiguous.length;row.classList.toggle('needs-review',!!needs);for(const [key,input] of Object.entries(inputs))input.classList.toggle('uncertain',ambiguous.includes(key));hint.textContent=[...r.issues,...ambiguous.map(k=>({name:'اسم الصنف',quantity:'الكمية',unit_price:'السعر',line_total:'الإجمالي'})[k]+' غير مؤكد'),r.diff!=null&&r.diff!==0n?'فرق حسابي يحتاج تصحيحاً أو توضيحاً':'',item.reading_note||''].filter(Boolean).join(' / ');label.hidden=!needs;note.hidden=!(r.diff!=null&&r.diff!==0n);invoiceTotals()}
  for(const [key,input] of Object.entries(inputs))input.addEventListener('input',()=>{item[key]=input.value;item.reviewed=false;check.checked=false;$('invTotalReviewed').checked=false;invoiceInvalidate();refresh()});
  check.addEventListener('change',()=>{item.reviewed=check.checked;invoiceInvalidate()});note.addEventListener('input',()=>{item.review_note=note.value;item.reviewed=false;check.checked=false;invoiceInvalidate()});
  const remove=document.createElement('td');remove.append(actionButton('حذف',()=>{invoiceState.items.splice(index,1);$('invTotalReviewed').checked=false;renderInvoice()}));row.append(remove);body.append(row);refresh();
 });
 $('invoiceWarnings').replaceChildren(...(invoiceState.source_warnings||[]).map(w=>textNode('small',w)));invoiceTotals();
}
$('addInvoiceRow').addEventListener('click',()=>{if(!invoiceState||invoiceState.items.length>=120)return;invoiceState.items.push({name:'',quantity:null,unit_price:null,line_total:null,uncertain_fields:[]});renderInvoice()});
for(const id of ['invSupplier','invNumber','invDate','invCurrency','invTotal','invDiscount','invTax','invCharges'])$(id).addEventListener('input',()=>{$('invTotalReviewed').checked=false;invoiceInvalidate();invoiceTotals()});
$('invTotalNote').addEventListener('input',()=>{$('invTotalReviewed').checked=false;invoiceInvalidate()});$('invTotalReviewed').addEventListener('change',invoiceInvalidate);
$('exportInvoice').addEventListener('click',async()=>{
 if(!invoiceState||busy)return;if(!$('invoiceConfirmed').checked){status.textContent='راجع الأسماء والأرقام وأكّد المراجعة أولاً.';return}
 const totals=invoiceTotals();if(!totals?.complete){status.textContent='أكمل البيانات والأرقام غير الصالحة أولاً.';return}
 for(const [index,item] of invoiceState.items.entries()){const r=InvoiceMath.row(item),different=r.diff!=null&&r.diff!==0n;if(((item.uncertain_fields||[]).length||different)&&!item.reviewed){status.textContent='أكد مراجعة السطر '+(index+1)+' أمام الأصل.';return}if(different&&!String(item.review_note||'').trim()){status.textContent='صحح فرق السطر '+(index+1)+' أو اكتب سبب اختلافه.';return}}
 if(totals.difference!=null&&totals.difference!==0n&&(!$('invTotalReviewed').checked||!$('invTotalNote').value.trim())){status.textContent='صحح فرق الإجمالي أو أكّد مراجعته واكتب سبب الاختلاف.';return}
 const button=$('exportInvoice'),snapshot=invoiceRevision;button.disabled=$('invoiceFile').disabled=$('scanInvoice').disabled=true;busy=true;update();
 try{const data=await featureAPI('/invoice/export',{method:'POST',body:JSON.stringify({reviewed:true,invoice:currentInvoice(),document:$('invoiceIncludeSource').checked?invoiceOriginalDocument:null})});if(snapshot!==invoiceRevision){status.textContent='تغيّرت البيانات أثناء التصدير؛ صدّر النسخة المعدلة من جديد.';return}const card=textNode('div',data.reply,'feature-card');$('invoiceDownload').replaceChildren(card);showFile(card,data.file);status.textContent='تم تجهيز ملف Excel المنسق.'}catch(error){featureError(error)}finally{busy=false;button.disabled=$('invoiceFile').disabled=$('scanInvoice').disabled=false;update()}
});

$('invoiceIncludeSource').addEventListener('change',invoiceInvalidate);

// Review is a concrete user action, including when OCR was requested in chat.
function showInvoiceReview(el,invoice){
 const sourcePhoto=pendingPhotoOriginal,sourceDocument=pendingDocument;
 const card=textNode('div','','feature-card');card.append(textNode('strong','الفاتورة تحتاج مراجعة قبل Excel'));
 const flagged=invoice.items.map((r,i)=>(r.uncertain_fields?.length||r.issues?.length)?String(i+1):'').filter(Boolean);card.append(textNode('small',flagged.length?'السطور المعنية: '+flagged.join('، '):'راجع البيانات والمجموع أمام الأصل.'));
 card.append(actionButton('فتح مراجعة الفاتورة',()=>{
  const draft={invoice,created:Date.now()};let document=null;
  if(typeof sourcePhoto==='string'){const m=sourcePhoto.match(/^data:image\/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)$/);if(m)document={name:'invoice.'+(m[1]==='jpeg'?'jpg':m[1]),data:m[2]}}
  else if(sourceDocument&&/\.pdf$/i.test(sourceDocument.name||''))document=sourceDocument;
  try{sessionStorage.setItem('proInvoiceReviewDraft',JSON.stringify(draft));try{if(document)sessionStorage.setItem('proInvoiceReviewSource',JSON.stringify(document));else sessionStorage.removeItem('proInvoiceReviewSource')}catch(_){sessionStorage.removeItem('proInvoiceReviewSource')}window.location.assign('/invoices')}catch(_){throw new Error('تعذر نقل المراجعة في هذا المتصفح؛ افتح صفحة الفواتير وارفع الأصل مباشرة.')}
 }));el.append(card);
}
function restoreInvoiceReviewDraft(){
 if(PRO_PAGE!=='invoices')return;
 let draft,document;try{const raw=sessionStorage.getItem('proInvoiceReviewDraft');if(!raw)return;draft=JSON.parse(raw);document=JSON.parse(sessionStorage.getItem('proInvoiceReviewSource')||'null');sessionStorage.removeItem('proInvoiceReviewDraft');sessionStorage.removeItem('proInvoiceReviewSource')}catch(_){return}
 if(!draft?.invoice||!Array.isArray(draft.invoice.items)||Date.now()-draft.created>3600000)return;
 invoiceState=draft.invoice;invoiceOriginalDocument=document;
 for(const [id,key] of [['invSupplier','supplier'],['invNumber','invoice_number'],['invDate','date'],['invCurrency','currency'],['invTotal','printed_total'],['invDiscount','discount'],['invTax','tax'],['invCharges','charges']])$(id).value=invoiceState[key]??(invoiceState.metadata_uncertain?.includes(key)?invoiceState.raw_metadata?.[key]:'')??'';
 $('invTotalNote').value='';$('invTotalReviewed').checked=false;$('invoiceQuality').textContent='بيانات من الدردشة — راجع الخانات المميزة قبل التصدير';
 const source=$('invoiceSource');source.replaceChildren();
 if(document&&typeof document.data==='string'&&document.data.length<9*1024*1024){
  try{const binary=atob(document.data),bytes=Uint8Array.from(binary,c=>c.charCodeAt(0)),ext=(document.name||'').split('.').pop().toLowerCase(),mime={jpg:'image/jpeg',jpeg:'image/jpeg',png:'image/png',webp:'image/webp',pdf:'application/pdf'}[ext];if(!mime)throw Error('type');invoiceSourceURL=URL.createObjectURL(new Blob([bytes],{type:mime}));const link=textNode('a','فتح الأصل للمقارنة');link.href=invoiceSourceURL;link.target='_blank';link.rel='noopener';source.append(link);if(mime.startsWith('image/')){const image=new Image();image.src=invoiceSourceURL;image.alt='أصل الفاتورة من الدردشة';source.append(image)}}catch(_){invoiceOriginalDocument=null}
 }
 if(!invoiceOriginalDocument)source.append(textNode('small','الأصل غير منقول؛ قارنه بالنسخة الموجودة عندك أو ارفع الفاتورة مباشرة لإعادة القراءة.'));
 $('invoiceIncludeSource').checked=!!invoiceOriginalDocument;$('invoiceIncludeSource').disabled=!invoiceOriginalDocument;
 renderInvoice();$('invoiceReview').hidden=false;status.textContent='صحح الاسم أو الأرقام المميزة، وأكّد «راجعت السطر أمام الأصل» ثم التأكيد العام والتصدير.';
}
restoreInvoiceReviewDraft();
