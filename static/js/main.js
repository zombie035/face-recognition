const video = document.getElementById('video');
const canvas = document.createElement('canvas');
canvas.width = 640; canvas.height = 480;
const ctx = canvas.getContext('2d');
let streaming = false;

async function startCamera(){
  try{
    const stream = await navigator.mediaDevices.getUserMedia({video:true, audio:false});
    video.srcObject = stream;
    await video.play();
    streaming = true;
    document.getElementById('cameraStatus').innerText = 'Camera active';
  }catch(e){
    document.getElementById('cameraStatus').innerText = 'Camera access denied';
  }
}

function grabFrame(){
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.8);
}

// simple motion-based liveness check: capture two frames and compute diff
function motionLivenessCheck(){
  return new Promise((resolve)=>{
    const a = grabFrame();
    setTimeout(()=>{
      const b = grabFrame();
      // compare pixels
      const imgA = new Image();
      const imgB = new Image();
      let loaded = 0;
      imgA.onload = ()=>{ if(++loaded==2) compare(); }
      imgB.onload = ()=>{ if(++loaded==2) compare(); }
      imgA.src = a; imgB.src = b;
      function compare(){
        const c1 = document.createElement('canvas'); c1.width=640;c1.height=480; const g1=c1.getContext('2d'); g1.drawImage(imgA,0,0);
        const c2 = document.createElement('canvas'); c2.width=640;c2.height=480; const g2=c2.getContext('2d'); g2.drawImage(imgB,0,0);
        const d1 = g1.getImageData(0,0,640,480).data;
        const d2 = g2.getImageData(0,0,640,480).data;
        let diff = 0;
        for(let i=0;i<d1.length;i+=4){
          diff += Math.abs(d1[i] - d2[i]);
          if(i>640*480*4) break; // limit
        }
        // normalize
        const avg = diff / (640*480);
        resolve(avg > 8); // threshold
      }
    }, 800);
  });
}

async function recognize(){
  if(!streaming) return alert('Camera not active');
  const img = grabFrame();
  const res = await fetch('/recognize', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({image: img})});
  const j = await res.json();
  const nameEl = document.getElementById('user-name') || document.getElementById('name');
  if(nameEl) nameEl.innerText = j.name || '-';
  document.getElementById('confidence').innerText = (j.confidence || 0) + '%';
  return j;
}

async function captureFlow(){
  if(!streaming) return alert('Camera not active');
  document.getElementById('btnCapture').disabled = true;
  const live = await motionLivenessCheck();
  if(!live){ alert('Liveness check failed. Please move slightly and try again.'); document.getElementById('btnCapture').disabled = false; return; }
  const recog = await recognize();
  const img = grabFrame();
  const payload = {image: img, user_name: recog.name, user_id: null, confidence: recog.confidence};
  const res = await fetch('/capture', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const j = await res.json();
  if(j.photo_id) alert('Photo uploaded. id:' + j.photo_id);
  document.getElementById('btnCapture').disabled = false;
}

async function enrollFlow(){
  if(!streaming) return alert('Camera not active');
  const name = prompt('Enter your name for enrollment');
  if(!name) return;
  const images = [];
  for(let i=0;i<10;i++){
    alert('Please position face for sample ' + (i+1) + ' and press OK');
    images.push(grabFrame());
    await new Promise(r=>setTimeout(r,300));
  }
  const res = await fetch('/register', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name: name, images: images})});
  const j = await res.json();
  if(j.user_id) alert('Registered user id: ' + j.user_id);
}

document.getElementById('btnRecognize').onclick = recognize;
document.getElementById('btnCapture').onclick = captureFlow;
document.getElementById('btnRegister').onclick = enrollFlow;

startCamera();