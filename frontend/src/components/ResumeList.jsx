import React from 'react';

const ResumeList = ({ items = [], title, onSelect, selected }) => (
  <div className="rounded-lg bg-slate-900 p-4 shadow">
    <h3 className="text-lg font-semibold text-slate-200">{title}</h3>
    {items.length === 0 ? (
      <p className="mt-2 text-sm text-slate-400">No items uploaded yet.</p>
    ) : (
      <ul className="mt-3 space-y-2">
        {items.map((item) => {
          const isSelected = selected && item.key === selected.key;
          return (
            <li
              key={item.key}
              className={`flex items-center justify-between rounded border px-3 py-2 text-sm text-slate-100 ${isSelected ? 'border-emerald-400 bg-emerald-950' : 'border-slate-800 bg-slate-950'}`}
            >
              <span className="truncate pr-2">{item.fileName}</span>
              {onSelect && (
                <button
                  type="button"
                  onClick={() => onSelect(item)}
                  className={`rounded px-2 py-1 text-xs font-semibold ${isSelected ? 'bg-emerald-400 text-slate-900' : 'bg-emerald-500 text-slate-900 hover:bg-emerald-400'}`}
                >
                  {isSelected ? 'Selected' : 'Select'}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    )}
  </div>
);

export default ResumeList;
