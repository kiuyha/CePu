import React from 'react';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content, className = '' }) => {
  // Parse markdown ke elemen React sederhana tanpa library eksternal
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let currentList: string[] = [];

  const flushList = (keyPrefix: number) => {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`ul-${keyPrefix}`} style={{ paddingLeft: '20px', marginBottom: '14px' }}>
          {currentList.map((item, idx) => (
            <li key={idx} style={{ marginBottom: '6px', lineHeight: 1.6 }}>
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );
      currentList = [];
    }
  };

  const renderInline = (text: string): React.ReactNode[] => {
    // Parser inline untuk **bold**, *italic*, dan `code`
    const parts: React.ReactNode[] = [];
    const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }
      const raw = match[0];
      if (raw.startsWith('**') && raw.endsWith('**')) {
        parts.push(<strong key={match.index} style={{ fontWeight: 700 }}>{raw.slice(2, -2)}</strong>);
      } else if (raw.startsWith('*') && raw.endsWith('*')) {
        parts.push(<em key={match.index}>{raw.slice(1, -1)}</em>);
      } else if (raw.startsWith('`') && raw.endsWith('`')) {
        parts.push(
          <code 
            key={match.index} 
            style={{ 
              background: 'rgba(56, 152, 236, 0.1)', 
              color: '#3898EC', 
              padding: '2px 6px', 
              borderRadius: '4px',
              fontSize: '0.9em' 
            }}
          >
            {raw.slice(1, -1)}
          </code>
        );
      }
      lastIndex = match.index + raw.length;
    }

    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }

    return parts.length > 0 ? parts : [text];
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();

    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      currentList.push(trimmed.slice(2));
      return;
    }

    flushList(index);

    if (trimmed.startsWith('### ')) {
      elements.push(
        <h3 key={index} style={{ fontSize: '16px', fontWeight: 700, marginTop: '18px', marginBottom: '8px', color: 'var(--primary-text)' }}>
          {renderInline(trimmed.slice(4))}
        </h3>
      );
    } else if (trimmed.startsWith('## ')) {
      elements.push(
        <h2 key={index} style={{ fontSize: '19px', fontWeight: 800, marginTop: '22px', marginBottom: '10px', color: '#3898EC' }}>
          {renderInline(trimmed.slice(3))}
        </h2>
      );
    } else if (trimmed.startsWith('# ')) {
      elements.push(
        <h1 key={index} style={{ fontSize: '22px', fontWeight: 800, marginTop: '24px', marginBottom: '12px', color: 'var(--primary-text)' }}>
          {renderInline(trimmed.slice(2))}
        </h1>
      );
    } else if (trimmed === '') {
      // Empty line / paragraph break
      elements.push(<div key={index} style={{ height: '8px' }} />);
    } else {
      elements.push(
        <p key={index} style={{ fontSize: '14.5px', lineHeight: 1.7, marginBottom: '10px', color: 'var(--secondary-text)' }}>
          {renderInline(trimmed)}
        </p>
      );
    }
  });

  flushList(lines.length);

  return <div className={`markdown-body ${className}`}>{elements}</div>;
};
