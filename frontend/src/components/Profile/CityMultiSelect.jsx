import { useState, useRef, useEffect } from "react";
import { X, ChevronDown, Search } from "lucide-react";
import { INDIA_CITIES } from "../../lib/india-cities";

// Searchable multi-select over the India cities list. Value is an array of
// city strings; onChange receives the next array.
export default function CityMultiSelect({ value = [], onChange }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef(null);

  useEffect(() => {
    function handler(e) {
      if (!ref.current?.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = INDIA_CITIES.filter(
    (c) => c.toLowerCase().includes(search.toLowerCase()) && !value.includes(c)
  );

  function add(city) {
    onChange([...value, city]);
    setSearch("");
  }
  function remove(city) {
    onChange(value.filter((c) => c !== city));
  }

  return (
    <div className="relative" ref={ref}>
      <div
        onClick={() => setOpen(true)}
        className="min-h-[42px] flex flex-wrap gap-1.5 p-2 input-glass cursor-text"
      >
        {value.map((city) => (
          <span key={city} className="pill pill-brand">
            {city}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); remove(city); }}
              className="hover:opacity-60"
              aria-label={`Remove ${city}`}
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <span className="inline-flex items-center gap-1 text-[13px] text-muted-foreground">
          {value.length === 0 && "Select cities…"}
          <ChevronDown size={14} />
        </span>
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-full glass-strong rounded-xl max-h-56 overflow-hidden flex flex-col">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
            <Search size={14} className="text-muted-foreground" />
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search cities…"
              className="flex-1 bg-transparent text-[13px] outline-none text-foreground"
            />
          </div>
          <div className="overflow-y-auto flex-1">
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-[13px] text-muted-foreground">No cities found</p>
            ) : (
              filtered.map((city) => (
                <button
                  key={city}
                  type="button"
                  onClick={() => add(city)}
                  className="flex w-full items-center px-3 py-2 text-[13px] text-foreground hover:bg-muted transition-colors"
                >
                  {city}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
