'use strict';
(() => {
  const eventChoice=$('editor-event'),board=$('image-editor-board');
  let events=[],draft=null,selected=null,loadedRoom=null,busy=false,dirty=false,requestRevision=0,tool='select';
  const roomId=()=>events.find(e=>e.id===eventChoice.value)?.schedule?.room_id||'';
  const message=text=>$('image-editor-message').textContent=text;
  const readOnly=()=>!!draft?.locked||draft?.type!=='image';
  function validRoom(){if(roomId()!==loadedRoom)throw Error('Ca đã đổi; hãy tải lại.');}
  function state(value){
    busy=value;eventChoice.disabled=value;$('image-map-file').disabled=value||!!draft?.locked;$('image-map-min-area').disabled=value||!!draft?.locked;$('image-map-load').disabled=value;$('image-map-detect').disabled=value||!!draft?.locked;
    for(const id of ['image-map-save','image-region-apply','image-region-delete','room-tool-select','room-tool-add'])$(id).disabled=value||!draft||readOnly();
    for(const id of ['image-region-label','image-region-capacity'])$(id).disabled=value||readOnly();
  }
  function chooseTool(value){tool=value;selected=null;draw();}
  function overlap(a,b){
    for(const p of [a,b])for(let i=0;i<4;i++){
      const q=p[(i+1)%4],axis=[-(q[1]-p[i][1]),q[0]-p[i][0]],project=v=>v[0]*axis[0]+v[1]*axis[1];
      const x=a.map(project),y=b.map(project);
      if(Math.min(Math.max(...x),Math.max(...y))-Math.max(Math.min(...x),Math.min(...y))<=.001)return false;
    }
    return true;
  }
  function attachDrawing(svg){
    for(const event of ['onpointerdown','onpointermove','onpointerup','onpointercancel','onlostpointercapture','onkeydown'])svg[event]=null;
    svg.dataset.tool=tool;if(tool!=='add'||busy||readOnly())return;
    let start=null,preview=null,pointer=null;
    const point=event=>{const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;const q=p.matrixTransform(svg.getScreenCTM().inverse());return [Math.max(0,Math.min(draft.columns-1,Math.round(q.x))),Math.max(0,Math.min(draft.rows-1,Math.round(q.y)))];};
    const clear=()=>{preview?.remove();preview=null;start=null;pointer=null;};
    svg.onpointerdown=event=>{
      if(event.button!==0||start)return;event.preventDefault();svg.setAttribute('tabindex','0');svg.focus({preventScroll:true});start=point(event);pointer=event.pointerId;svg.setPointerCapture(pointer);
      preview=document.createElementNS('http://www.w3.org/2000/svg','rect');preview.setAttribute('class','room-drag-preview');svg.append(preview);
    };
    svg.onpointermove=event=>{
      if(!start||event.pointerId!==pointer)return;const end=point(event);
      preview.setAttribute('x',Math.min(start[0],end[0]));preview.setAttribute('y',Math.min(start[1],end[1]));preview.setAttribute('width',Math.abs(end[0]-start[0]));preview.setAttribute('height',Math.abs(end[1]-start[1]));
    };
    svg.onpointerup=event=>{
      if(!start||event.pointerId!==pointer)return;const end=point(event),x=Math.min(start[0],end[0]),y=Math.min(start[1],end[1]),w=Math.abs(end[0]-start[0]),h=Math.abs(end[1]-start[1]);
      svg.releasePointerCapture(pointer);clear();if(w<4||h<4){message('Kéo một vùng phòng lớn hơn.');return;}
      const points=[[x,y],[x+w,y],[x+w,y+h],[x,y+h]];
      if(draft.elements.some(r=>r.points&&overlap(points,r.points))){message('Phòng mới chồng lên phòng khác.');return;}
      const id='m'+crypto.randomUUID().replaceAll('-','').slice(0,24);
      draft.elements.push({id,kind:'zone',points,x,y,width:w,height:h,label:'',capacity:null});selected=id;dirty=true;tool='select';draw();$('image-region-label').focus();
    };
    svg.onpointercancel=clear;svg.onlostpointercapture=()=>{if(start)clear();};
    svg.onkeydown=event=>{if(event.key==='Escape'){clear();chooseTool('select');}};
  }
  function draw(){
    if(!draft)return;
    if(draft.type!=='image'){state(busy);return;}
    const layout={...draft,columns:draft.columns||draft.width,rows:draft.rows||draft.height,elements:draft.elements||draft.regions};
    renderImageMap(board,layout,null,false,region=>{if(tool==='add')return;selected=region.id;draw();},selected);
    attachDrawing(board.querySelector('svg'));
    const region=layout.elements.find(r=>r.id===selected);$('image-region-properties').hidden=!region;
    if(region){$('image-region-label').value=region.label||'';$('image-region-capacity').value=region.capacity??'';}
    $('room-tool-select').setAttribute('aria-pressed',String(tool==='select'));$('room-tool-add').setAttribute('aria-pressed',String(tool==='add'));
    $('room-tool-hint').textContent=tool==='add'?'Kéo trên ảnh để thêm phòng.':'';
    state(busy);
    message(`${layout.elements.length} phòng${dirty?' · Chưa lưu':''}${draft.locked?' · Đã khóa':''}`);
  }
  $('room-tool-select').onclick=()=>chooseTool('select');$('room-tool-add').onclick=()=>chooseTool('add');
  $('image-map-load').onclick=action(async()=>{
    if(dirty&&!confirm('Bỏ cấu hình phòng chưa lưu?'))return;
    const id=roomId();if(!id)throw Error('Chọn ca có lịch diễn ra.');
    const version=++requestRevision;state(true);
    try{
      const layout=await api(`/rooms/${id}/seat-map`);if(roomId()!==id||version!==requestRevision)return;
      loadedRoom=id;selected=null;dirty=false;tool='select';draft=layout;
      if(layout.type==='image')draw();else{renderSeatMap(board,layout,null,false);message('Chưa có sơ đồ ảnh. Tải ảnh để thiết lập phòng.');$('image-region-properties').hidden=true;}
    }finally{if(version===requestRevision)state(false);}
  });
  $('image-map-detect').onclick=action(async()=>{
    const file=$('image-map-file').files[0],id=roomId();if(!id||!file)throw Error('Chọn ca và ảnh sơ đồ.');
    if(file.size>5*1024*1024)throw Error('Ảnh sơ đồ tối đa 5 MB');
    if(dirty&&!confirm('Bỏ các thay đổi phòng chưa lưu?'))return;
    const version=++requestRevision;state(true);message('Đang nhận diện tứ giác khép kín…');
    try{
      const body=new FormData();body.append('file',file);body.append('min_area',$('image-map-min-area').value);
      const result=await api(`/admin/rooms/${id}/seat-map/image`,'POST',body);if(roomId()!==id||version!==requestRevision)return;
      draft={...result,type:'image',columns:result.width,rows:result.height,elements:result.regions.map((r,i)=>({...r,kind:'zone',label:`Phòng ${i+1}`,capacity:null}))};
      loadedRoom=id;selected=null;dirty=true;tool='select';draw();
    }finally{if(version===requestRevision)state(false);}
  });
  function editSelected(){
    if(!draft||readOnly()||busy)return;const region=draft.elements.find(r=>r.id===selected);if(!region)return;
    region.label=$('image-region-label').value.trim();region.capacity=$('image-region-capacity').value===''?null:Number($('image-region-capacity').value);dirty=true;
  }
  $('image-region-label').oninput=editSelected;$('image-region-capacity').oninput=editSelected;
  const validate=region=>{if(!region.label.trim())throw Error('Nhập tên cho tất cả phòng.');if(!Number.isInteger(region.capacity)||region.capacity<1||region.capacity>100000)throw Error('Nhập số người cho mỗi phòng (1–100.000).');};
  $('image-region-apply').onclick=action(async()=>{validRoom();if(!draft||readOnly()||busy)return;editSelected();const region=draft.elements.find(r=>r.id===selected);if(region)validate(region);draw();});
  $('image-region-delete').onclick=()=>{if(!draft||readOnly()||busy)return;draft.elements=draft.elements.filter(r=>r.id!==selected);selected=null;dirty=true;draw();};
  $('image-map-save').onclick=action(async()=>{
    validRoom();if(!draft||readOnly()||busy)return;
    if(draft.type!=='image'||!draft.image_key)throw Error('Tải ảnh sơ đồ trước khi lưu.');
    if(!draft.elements.length)throw Error('Cần ít nhất một phòng.');
    editSelected();draft.elements.forEach(validate);
    if(new Set(draft.elements.map(r=>r.label)).size!==draft.elements.length)throw Error('Tên phòng không được trùng.');
    const version=++requestRevision,id=loadedRoom;state(true);
    try{
      const payload={revision:draft.revision,image_key:draft.image_key,min_area:draft.min_area??400,regions:draft.elements.map(r=>({id:r.id,kind:'zone',label:r.label,capacity:r.capacity,points:r.points}))};
      const result=await api(`/admin/rooms/${id}/seat-map/image`,'PUT',payload);if(roomId()!==id||version!==requestRevision)return;
      draft=result;dirty=false;draw();notice('Đã lưu sơ đồ phòng.');await catalogue();
    }finally{if(version===requestRevision)state(false);}
  });
  function reset(){requestRevision++;draft=null;selected=null;dirty=false;tool='select';board.replaceChildren();$('image-region-properties').hidden=true;$('image-map-file').value='';message('');state(false);}
  eventChoice.addEventListener('change',()=>{if(dirty&&!confirm('Bỏ cấu hình phòng chưa lưu?')){eventChoice.value=events.find(e=>e.schedule?.room_id===loadedRoom)?.id||'';return;}reset();});
  window.addEventListener('labseat-events',event=>{events=event.detail;const selected=eventChoice.value;eventChoice.replaceChildren(new Option('Chọn ca',''),...events.filter(e=>e.schedule?.room_id).map(e=>new Option(e.name,e.id)));eventChoice.value=selected;if(selected&&!eventChoice.value)reset();});
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  state(false);
})();
