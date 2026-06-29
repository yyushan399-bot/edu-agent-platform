import { useCallback, useRef, useState, type DragEvent } from "react";

interface Props {
  accept: string;
  multiple?: boolean;
  disabled?: boolean;
  onFilesSelected: (files: File[]) => void;
  emptyLabel: string;
  hint?: string;
  selectedLabel?: string;
  iconClass?: string;
  className?: string;
}

function extensionsFromAccept(accept: string): string[] {
  return accept
    .split(",")
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean);
}

function isAcceptedFile(file: File, accept: string): boolean {
  const extensions = extensionsFromAccept(accept);
  if (extensions.length === 0) return true;

  const name = file.name.toLowerCase();
  const ext = name.includes(".") ? `.${name.split(".").pop()}` : "";

  return extensions.some((rule) => {
    if (rule.startsWith(".")) return ext === rule;
    if (rule.endsWith("/*")) {
      const prefix = rule.slice(0, -1);
      return file.type.startsWith(prefix);
    }
    return file.type === rule;
  });
}

function filterAcceptedFiles(files: FileList | File[], accept: string): File[] {
  return Array.from(files).filter((file) => isAcceptedFile(file, accept));
}

export default function FileDropZone({
  accept,
  multiple = false,
  disabled = false,
  onFilesSelected,
  emptyLabel,
  hint = "点击选择或拖拽文件到此处",
  selectedLabel,
  iconClass = "fa-cloud-arrow-up",
  className = "",
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const applyFiles = useCallback(
    (incoming: FileList | File[]) => {
      const valid = filterAcceptedFiles(incoming, accept);
      if (valid.length === 0) return;
      onFilesSelected(multiple ? valid : [valid[0]]);
    },
    [accept, multiple, onFilesSelected]
  );

  const handleDragEnter = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) setDragOver(true);
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) {
      e.dataTransfer.dropEffect = "copy";
      setDragOver(true);
    }
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (disabled || !e.dataTransfer.files.length) return;
    applyFiles(e.dataTransfer.files);
  };

  const openPicker = () => {
    if (!disabled) inputRef.current?.click();
  };

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      onClick={openPicker}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openPicker();
        }
      }}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`w-full border-2 border-dashed rounded-lg p-6 text-center transition-colors cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-blue-400 ${
        disabled
          ? "opacity-60 cursor-not-allowed border-slate-200 bg-slate-50"
          : dragOver
            ? "border-blue-500 bg-blue-50"
            : "border-slate-300 hover:border-blue-400 hover:bg-blue-50/60"
      } ${className}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) applyFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <i className={`fa-solid ${iconClass} text-2xl mb-2 ${dragOver ? "text-blue-500" : "text-slate-400"}`} />
      <p className="text-sm text-slate-600">{selectedLabel || emptyLabel}</p>
      {!selectedLabel && (
        <p className="text-xs text-slate-400 mt-1">{hint}</p>
      )}
    </div>
  );
}

export { filterAcceptedFiles, isAcceptedFile };
