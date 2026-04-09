import React, { useState, useEffect } from 'react';

function calculateTimeLeft(endDate) {
  const difference = new Date(endDate) - new Date();
  if (difference <= 0) return null;
  return {
    days:    Math.floor(difference / (1000 * 60 * 60 * 24)),
    hours:   Math.floor((difference / (1000 * 60 * 60)) % 24),
    minutes: Math.floor((difference / (1000 * 60)) % 60),
    seconds: Math.floor((difference / 1000) % 60),
  };
}

function TimeUnit({ value, label }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '22px', fontWeight: 700, color: '#fff', lineHeight: 1, fontFamily: 'JetBrains Mono, monospace' }}>
        {String(value).padStart(2, '0')}
      </div>
      <div style={{ fontSize: '10px', color: '#8b949e', marginTop: '4px', fontFamily: 'monospace' }}>
        {label}
      </div>
    </div>
  );
}

export default function CeasefireCountdown({ endDate }) {
  const [timeLeft, setTimeLeft] = useState(() => calculateTimeLeft(endDate));

  useEffect(() => {
    const timer = setInterval(() => setTimeLeft(calculateTimeLeft(endDate)), 1000);
    return () => clearInterval(timer);
  }, [endDate]);

  if (!timeLeft) {
    return <span style={{ color: '#f85149', fontWeight: 700, fontSize: '13px' }}>CEASEFIRE EXPIRED</span>;
  }

  return (
    <div style={{ display: 'flex', gap: '20px' }}>
      <TimeUnit value={timeLeft.days}    label="DAYS" />
      <TimeUnit value={timeLeft.hours}   label="HRS" />
      <TimeUnit value={timeLeft.minutes} label="MIN" />
      <TimeUnit value={timeLeft.seconds} label="SEC" />
    </div>
  );
}
