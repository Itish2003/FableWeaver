import { useState, useRef, useEffect } from 'react';

export default function EditableField({
  path,
  value,
  onSave,
  type = 'text',
  label,
  options = [],
  placeholder = 'Click to edit...',
  className = '',
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value ?? '');
  const inputRef = useRef(null);

  useEffect(() => {
    setEditValue(value ?? '');
  }, [value]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      if (type === 'text' || type === 'textarea') {
        inputRef.current.select?.();
      }
    }
  }, [isEditing, type]);

  const handleSave = async () => {
    if (editValue !== value) {
      await onSave(path, editValue);
    }
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditValue(value ?? '');
    setIsEditing(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && type !== 'textarea') {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  };

  // Display mode
  if (!isEditing) {
    const displayValue = value ?? '';
    const isEmpty = displayValue === '' || displayValue === null || displayValue === undefined;

    return (
      <div className={`mb-3 ${className}`}>
        {label && (
          <label className="text-xs text-gray-500 block mb-1 font-medium">{label}</label>
        )}
        <div
          onClick={() => setIsEditing(true)}
          className={`text-sm rounded-lg px-3 py-2 cursor-pointer transition-all border ${
            isEmpty
              ? 'text-gray-600 bg-white/5 border-white/5 hover:border-white/20'
              : 'text-gray-200 bg-white/5 border-white/10 hover:border-purple-500/50 hover:bg-white/10'
          }`}
        >
          {isEmpty ? placeholder : (
            type === 'textarea' ? (
              <span className="whitespace-pre-wrap">{displayValue}</span>
            ) : (
              displayValue
            )
          )}
        </div>
      </div>
    );
  }

  // Edit mode
  return (
    <div className={`mb-3 ${className}`}>
      {label && (
        <label className="text-xs text-gray-500 block mb-1 font-medium">{label}</label>
      )}
      <div className="flex flex-col gap-2">
        {type === 'select' ? (
          <select
            ref={inputRef}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="input-field text-sm"
          >
            {options.map((opt) => (
              <option key={opt.value ?? opt} value={opt.value ?? opt}>
                {opt.label ?? opt}
              </option>
            ))}
          </select>
        ) : type === 'textarea' ? (
          <textarea
            ref={inputRef}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="input-field text-sm min-h-[100px] resize-y"
            placeholder={placeholder}
          />
        ) : (
          <input
            ref={inputRef}
            type={type}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onKeyDown={handleKeyDown}
            className="input-field text-sm"
            placeholder={placeholder}
          />
        )}
        <div className="flex gap-2 justify-end">
          <button
            onClick={handleCancel}
            className="btn-secondary-sm"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="btn-primary-sm"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
