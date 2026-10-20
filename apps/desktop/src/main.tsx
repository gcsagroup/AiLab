import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';
import './preview.css';

const preview = import.meta.env.VITE_UI_PREVIEW === 'true';
if (preview) document.documentElement.classList.add('ui-preview');
createRoot(document.getElementById('root')!).render(<React.StrictMode>
  {preview && <div className="preview-banner" role="note">Windows UI 预览版 · 可浏览页面、编辑并保存本地草稿 · 模型运行、训练与下载尚未接入</div>}
  <App />
</React.StrictMode>);
