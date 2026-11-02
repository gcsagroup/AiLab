import { useState } from 'react';
import { ExternalLink, FlaskConical } from 'lucide-react';
import { isTauri } from '@tauri-apps/api/core';
import { errorMessage, openEnvironmentConsole } from '../api';
import { Error } from './common';

export default function EnvironmentCollection() {
  const [error, setError] = useState('');
  return <section className="st-environment-collection" aria-label="强化学习环境集">
    <div className="st-console-entry"><FlaskConical size={24} /><div><h2>强化学习环境</h2><p>192.168.9.101:8090</p></div>
      <a className="st-console-open" href="http://192.168.9.101:8090/" target="_blank" rel="noopener noreferrer" onClick={e => {
        if (!isTauri()) return;
        e.preventDefault(); setError(''); void openEnvironmentConsole().catch(err => setError(errorMessage(err)));
      }}><ExternalLink size={16} />打开控制界面</a>
    </div><p className="st-note">控制界面在独立窗口打开。</p><Error text={error} />
  </section>;
}
