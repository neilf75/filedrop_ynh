const POLL_INTERVAL_MS = 4000;

const whoamiEl = document.getElementById("whoami");
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const fileListEl = document.getElementById("file-list");
const emptyHintEl = document.getElementById("empty-hint");
const progressWrap = document.getElementById("upload-progress");
const progressBar = document.getElementById("upload-progress-bar");

function formatSize(bytes) {
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatAge(uploadedAtSeconds) {
  const ageSeconds = Date.now() / 1000 - uploadedAtSeconds;
  if (ageSeconds < 60) return "just now";
  if (ageSeconds < 3600) return `${Math.floor(ageSeconds / 60)}m ago`;
  return `${Math.floor(ageSeconds / 3600)}h ago`;
}

async function loadMe() {
  const res = await fetch("api/me");
  if (!res.ok) {
    whoamiEl.textContent = "Not logged in";
    return;
  }
  const data = await res.json();
  whoamiEl.textContent = `Logged in as ${data.display_name}`;
}

async function refreshFiles() {
  const res = await fetch("api/files");
  if (!res.ok) return;
  const files = await res.json();
  renderFiles(files);
}

function renderFiles(files) {
  fileListEl.innerHTML = "";
  emptyHintEl.classList.toggle("hidden", files.length > 0);

  for (const file of files) {
    const li = document.createElement("li");

    const info = document.createElement("div");
    info.className = "file-info";
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = file.filename;
    const meta = document.createElement("span");
    meta.className = "file-meta";
    meta.textContent = `${formatSize(file.size)} · uploaded ${formatAge(file.uploaded_at)}`;
    info.append(name, meta);

    const actions = document.createElement("div");
    actions.className = "file-actions";

    const downloadBtn = document.createElement("button");
    downloadBtn.className = "download";
    downloadBtn.textContent = "Download";
    downloadBtn.addEventListener("click", () => downloadFile(file));

    const deleteBtn = document.createElement("button");
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", () => deleteFile(file.id));

    actions.append(downloadBtn, deleteBtn);
    li.append(info, actions);
    fileListEl.append(li);
  }
}

async function downloadFile(file) {
  const res = await fetch(`api/files/${file.id}/download`);
  if (!res.ok) {
    alert("This file is no longer available (maybe already downloaded elsewhere).");
    refreshFiles();
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = file.filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  refreshFiles();
}

async function deleteFile(fileId) {
  await fetch(`api/files/${fileId}`, { method: "DELETE" });
  refreshFiles();
}

function uploadFile(file) {
  const xhr = new XMLHttpRequest();
  const formData = new FormData();
  formData.append("file", file);

  progressWrap.classList.remove("hidden");
  progressBar.style.width = "0%";

  xhr.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) {
      progressBar.style.width = `${Math.round((e.loaded / e.total) * 100)}%`;
    }
  });

  xhr.addEventListener("loadend", () => {
    progressWrap.classList.add("hidden");
    if (xhr.status >= 200 && xhr.status < 300) {
      refreshFiles();
    } else {
      alert("Upload failed.");
    }
  });

  xhr.open("POST", "api/upload");
  xhr.send(formData);
}

fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    uploadFile(fileInput.files[0]);
    fileInput.value = "";
  }
});

["dragenter", "dragover"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  })
);

["dragleave", "drop"].forEach((evt) =>
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
  })
);

dropZone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

loadMe();
refreshFiles();
setInterval(refreshFiles, POLL_INTERVAL_MS);
