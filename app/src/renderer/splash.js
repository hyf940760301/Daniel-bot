'use strict'

const statusEl = document.getElementById('status')

function setStatus(text) {
  if (typeof text === 'string' && text.trim()) statusEl.textContent = text
}

if (window.daniel) {
  window.daniel.onStatus(setStatus)
}
