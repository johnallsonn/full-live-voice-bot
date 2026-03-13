'use client';

import React from 'react';
import { useDataChannel } from '@livekit/components-react';
import { cn } from '@/lib/utils';

interface RealtimeTextProps {
  className?: string;
}

export function RealtimeText({ className }: RealtimeTextProps) {
  const [userText, setUserText] = React.useState<string>('');
  const [agentText, setAgentText] = React.useState<string>('');
  const [agentFinal, setAgentFinal] = React.useState<boolean>(false);
  const [history, setHistory] = React.useState<Array<{ role: 'user' | 'agent'; text: string }>>([]);
  const agentStreamingRef = React.useRef<boolean>(false);
  const lastFinalUserRef = React.useRef<string>('');
  const lastFinalAgentRef = React.useRef<string>('');

  // Support both custom and LiveKit default transcription topics
  useDataChannel('lk.transcription', (msg) => {
    try {
      const payload = JSON.parse(new TextDecoder().decode(msg.payload));
      const txt = typeof payload?.text === 'string' ? payload.text : '';
      const isFinal = !!payload?.is_final;
      if (!txt) return;
      if (isFinal) {
        if (txt !== lastFinalUserRef.current) {
          setHistory((h) => [...h, { role: 'user', text: txt }]);
          lastFinalUserRef.current = txt;
        }
        setUserText('');
      } else {
        setUserText(txt);
      }
    } catch {
      // ignore malformed payloads
    }
  });

  useDataChannel('agent_response_partial', (msg) => {
    try {
      const payload = JSON.parse(new TextDecoder().decode(msg.payload));
      if (typeof payload?.text === 'string') {
        if (!agentStreamingRef.current) {
          agentStreamingRef.current = true;
          setAgentText('');
        }
        setAgentText((prev) => prev + payload.text);
        setAgentFinal(false);
      }
    } catch {
      // ignore malformed payloads
    }
  });

  useDataChannel('agent_response', (msg) => {
    try {
      const raw = new TextDecoder().decode(msg.payload);
      let txt = '';
      try {
        const payload = JSON.parse(raw);
        if (typeof payload?.text === 'string') {
          txt = payload.text;
        }
      } catch {
        txt = raw || '';
      }
      if (txt) {
        const isNewFinal = txt !== lastFinalAgentRef.current;
        if (isNewFinal) {
          setHistory((h) => [...h, { role: 'agent', text: txt }]);
          lastFinalAgentRef.current = txt;
        }
        setAgentText('');
        agentStreamingRef.current = false;
        setAgentFinal(true);
        if (isNewFinal && typeof window !== 'undefined' && 'speechSynthesis' in window) {
          try {
            if (window.speechSynthesis.speaking) {
              window.speechSynthesis.cancel();
            }
            const u = new SpeechSynthesisUtterance(txt);
            u.rate = 1;
            u.pitch = 1;
            u.volume = 1;
            u.lang = 'en-US';
            window.speechSynthesis.speak(u);
          } catch {}
        }
      }
    } catch {
      // ignore malformed payloads
    }
  });

  return (
    <div
      className={cn(
        'bg-background/70 pointer-events-none mx-auto max-w-2xl rounded-md p-3 backdrop-blur',
        className
      )}
    >
      <ul className="space-y-1">
        {history.map((m, i) => (
          <li key={i} className="text-sm break-words">
            <span className="text-muted-foreground font-mono text-xs">
              {m.role === 'user' ? 'You' : 'Agent'}
            </span>
            <div className="text-foreground">{m.text}</div>
          </li>
        ))}
      </ul>

      {userText && (
        <div className="text-sm break-words">
          <span className="text-muted-foreground font-mono text-xs">You</span>
          <div className="text-foreground">{userText}</div>
        </div>
      )}

      {agentText && (
        <div className="text-sm break-words">
          <span className="text-muted-foreground font-mono text-xs">Agent</span>
          <div className="text-foreground">
            {agentText}
            {!agentFinal && <span className="animate-pulse">▌</span>}
          </div>
        </div>
      )}
    </div>
  );
}
