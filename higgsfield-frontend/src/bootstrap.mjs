import { prepareBrowserCrypto } from '../../shared/browser/intranetCrypto.mjs'

prepareBrowserCrypto(() => import('webcrypto-liner/build/index.es.js'), () => import('node-forge'))
  .then(() => import('./main.ts'))
  .catch(() => {
    document.getElementById('app').textContent = '页面初始化失败，请刷新后重试。'
  })
