import { useState, useRef, useEffect } from "react";
import { X, ChevronDown, Search } from "lucide-react";
import { INDIA_CITIES, INDIA_LOCATION_OPTIONS } from "../../lib/india-cities";

export default function CityMultiSelect({ value = [], onChange }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef(null);

  useEffect(() => {
    function handler(event) {
      if (!ref.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const lowerSearch = search.toLowerCase();
  const remoteOptions = INDIA_LOCATION_OPTIONS.slice(0, 2).filter(
    (item) => item.toLowerCase().includes(lowerSearch) && !value.includes(item)
  );
  const cityOptions = INDIA_CITIES.filter(
    (city) => city.toLowerCase().includes(lowerSearch) && !value.includes(city)
  );

  function add(city) {
    const next = city.trim();
    if (!next || value.some((item) => item.toLowerCase() === next.toLowerCase())) return;
    onChange([...value, next]);
    setSearch("");
  }

  function remove(city) {
    onChange(value.filter((item) => item !== city));
  }

  const canAddCustom =
    search.trim() &&
    !INDIA_LOCATION_OPTIONS.some((item) => item.toLowerCase() === search.trim().toLowerCase()) &&
    !value.some((item) => item.toLowerCase() === search.trim().toLowerCase());

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
              onClick={(event) => { event.stopPropagation(); remove(city); }}
              className="hover:opacity-60"
              aria-label={`Remove ${city}`}
            >
              <X size={11} />
            </button>
          </span>
        ))}
        <span className="inline-flex items-center gap-1 text-[13px] text-muted-foreground">
          {value.length === 0 && "Search or select locations..."}
          <ChevronDown size={14} />
        </span>
      </div>

      {open && (
        <div className="absolute z-50 mt-1 w-full glass-strong rounded-xl max-h-72 overflow-hidden flex flex-col">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
            <Search size={14} className="text-muted-foreground" />
            <input
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search all India locations..."
              className="flex-1 bg-transparent text-[13px] outline-none text-foreground"
            />
          </div>
          <div className="overflow-y-auto flex-1">
            {remoteOptions.length > 0 && (
              <div className="border-b border-border py-1">
                <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Remote</p>
                {remoteOptions.map((city) => (
                  <button
                    key={city}
                    type="button"
                    onClick={() => add(city)}
                    className="flex w-full items-center px-3 py-2 text-[13px] text-foreground hover:bg-muted transition-colors"
                  >
                    {city}
                  </button>
                ))}
              </div>
            )}

            {cityOptions.length > 0 && (
              <>
                <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Cities</p>
                {cityOptions.map((city) => (
                  <button
                    key={city}
                    type="button"
                    onClick={() => add(city)}
                    className="flex w-full items-center px-3 py-2 text-[13px] text-foreground hover:bg-muted transition-colors"
                  >
                    {city}
                  </button>
                ))}
              </>
            )}

            {canAddCustom && (
              <button
                type="button"
                onClick={() => add(search)}
                className="flex w-full items-center px-3 py-2 text-[13px] font-semibold text-brand hover:bg-muted transition-colors"
              >
                Add "{search.trim()}"
              </button>
            )}

            {remoteOptions.length === 0 && cityOptions.length === 0 && !canAddCustom && (
              <div className="px-3 py-2 text-[13px] text-muted-foreground">No locations found</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
