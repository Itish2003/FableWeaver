import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function EditableArray({
  path,
  items = [],
  onSave,
  label,
  itemType = 'string', // 'string' | 'object'
  itemSchema = null, // For object arrays: { fieldName: { type, label, options } }
  emptyMessage = 'No items yet',
  className = '',
}) {
  const [localItems, setLocalItems] = useState(items || []);
  const [isEditing, setIsEditing] = useState(false);
  const [editingIndex, setEditingIndex] = useState(null);

  useEffect(() => {
    setLocalItems(items || []);
  }, [items]);

  const handleAddItem = () => {
    if (itemType === 'string') {
      setLocalItems([...localItems, '']);
      setEditingIndex(localItems.length);
    } else if (itemSchema) {
      const newItem = Object.keys(itemSchema).reduce((acc, key) => {
        acc[key] = itemSchema[key].default ?? '';
        return acc;
      }, {});
      setLocalItems([...localItems, newItem]);
      setEditingIndex(localItems.length);
    }
    setIsEditing(true);
  };

  const handleRemoveItem = async (index) => {
    const newItems = localItems.filter((_, i) => i !== index);
    setLocalItems(newItems);
    await onSave(path, newItems);
  };

  const handleUpdateItem = (index, value) => {
    const newItems = [...localItems];
    newItems[index] = value;
    setLocalItems(newItems);
  };

  const handleSave = async () => {
    // Filter out empty strings for string arrays
    const filteredItems = itemType === 'string'
      ? localItems.filter((item) => item && item.trim())
      : localItems;
    await onSave(path, filteredItems);
    setIsEditing(false);
    setEditingIndex(null);
  };

  const handleCancel = () => {
    setLocalItems(items || []);
    setIsEditing(false);
    setEditingIndex(null);
  };

  // Render string item
  const renderStringItem = (item, index) => {
    const isCurrentlyEditing = editingIndex === index;

    if (isCurrentlyEditing) {
      return (
        <input
          type="text"
          value={item}
          onChange={(e) => handleUpdateItem(index, e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              setEditingIndex(null);
            }
          }}
          className="flex-1 bg-black/60 border border-purple-500/50 rounded px-2 py-1 text-sm text-white focus:outline-none"
          autoFocus
        />
      );
    }

    return (
      <span
        onClick={() => { setEditingIndex(index); setIsEditing(true); }}
        className="flex-1 text-sm text-gray-300 cursor-pointer hover:text-white"
      >
        {item || 'Click to edit...'}
      </span>
    );
  };

  // Render object item
  const renderObjectItem = (item, index) => {
    const isCurrentlyEditing = editingIndex === index;

    if (isCurrentlyEditing && itemSchema) {
      return (
        <div className="flex-1 space-y-2">
          {Object.entries(itemSchema).map(([key, config]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="text-xs text-gray-500 w-24">{config.label || key}</label>
              {config.type === 'select' ? (
                <select
                  value={item[key] || ''}
                  onChange={(e) => handleUpdateItem(index, { ...item, [key]: e.target.value })}
                  className="flex-1 bg-black/60 border border-purple-500/50 rounded px-2 py-1 text-sm text-white"
                >
                  {config.options?.map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              ) : (
                <input
                  type={config.type || 'text'}
                  value={item[key] || ''}
                  onChange={(e) => handleUpdateItem(index, { ...item, [key]: e.target.value })}
                  className="flex-1 bg-black/60 border border-purple-500/50 rounded px-2 py-1 text-sm text-white focus:outline-none"
                  placeholder={config.placeholder}
                />
              )}
            </div>
          ))}
        </div>
      );
    }

    // Display mode for objects
    return (
      <div
        onClick={() => { setEditingIndex(index); setIsEditing(true); }}
        className="flex-1 cursor-pointer hover:bg-white/5 rounded p-1 -m-1"
      >
        {itemSchema ? (
          <div className="space-y-0.5">
            {Object.entries(itemSchema).slice(0, 3).map(([key, config]) => (
              <div key={key} className="flex gap-2 text-sm">
                <span className="text-gray-500">{config.label || key}:</span>
                <span className="text-gray-300">{item[key] || '-'}</span>
              </div>
            ))}
            {Object.keys(itemSchema).length > 3 && (
              <span className="text-xs text-gray-600">+ {Object.keys(itemSchema).length - 3} more fields</span>
            )}
          </div>
        ) : (
          <pre className="text-xs text-gray-400">{JSON.stringify(item, null, 2)}</pre>
        )}
      </div>
    );
  };

  return (
    <div className={`mb-4 ${className}`}>
      {label && (
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs text-gray-500 font-medium">{label}</label>
          <span className="text-xs text-gray-600">{localItems.length} items</span>
        </div>
      )}

      <div className="bg-white/5 rounded-lg border border-white/10 p-3">
        {localItems.length === 0 ? (
          <p className="text-sm text-gray-600 text-center py-2">{emptyMessage}</p>
        ) : (
          <div className="space-y-2">
            <AnimatePresence>
              {localItems.map((item, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-start gap-2 p-2 bg-black/20 rounded-lg"
                >
                  <span className="text-xs text-gray-600 mt-1 w-6">{index + 1}.</span>
                  {itemType === 'string'
                    ? renderStringItem(item, index)
                    : renderObjectItem(item, index)
                  }
                  <button
                    onClick={() => handleRemoveItem(index)}
                    className="p-1 text-gray-600 hover:text-red-400 transition-colors"
                    title="Remove"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}

        <div className="flex gap-2 mt-3 pt-3 border-t border-white/10">
          <button
            onClick={handleAddItem}
            className="flex-1 px-3 py-2 text-xs rounded-lg bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 transition-colors"
          >
            + Add Item
          </button>
          {isEditing && (
            <>
              <button
                onClick={handleCancel}
                className="px-3 py-2 text-xs rounded-lg bg-white/10 text-gray-400 hover:bg-white/20 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="px-3 py-2 text-xs rounded-lg bg-green-500/20 text-green-300 hover:bg-green-500/30 transition-colors"
              >
                Save All
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
