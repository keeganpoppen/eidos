<script lang="ts">
  import { onMount } from 'svelte';
  import { artifactKind } from './artifact-inputs';
  import { savedWork, catalogKey, catalogChoices, catalogSelection, type CatalogItem, type CatalogKind } from './saved-work';

  let { id, label, kind = 'catalog', value = '', selectedLabel = '', emptyLabel = 'Choose saved investigation', disabled = false, active = true, extra = [], onChoose }: {
    id: string; label: string; kind?: CatalogKind; value?: string; selectedLabel?: string; emptyLabel?: string;
    disabled?: boolean; active?: boolean; extra?: CatalogItem[]; onChoose: (value: string, item?: CatalogItem) => void;
  } = $props();
  let search = $state('');
  let query = $state('');
  let cursor = $state('');
  let previous = $state<string[]>([]);
  let next = $state<string | null>(null);
  let items = $state<CatalogItem[]>([]);
  let selected = $state<CatalogItem | undefined>();
  let loading = $state(false);
  let error = $state('');
  let generation = 0;
  const choices = $derived(catalogChoices([...items, ...extra.filter((item) => !items.some((other) => catalogKey(other) === catalogKey(item)))], selected && catalogKey(selected) === value ? selected : undefined));
  const selection = $derived(catalogSelection(items, value, selected));

  function itemLabel(item: CatalogItem): string {
    return 'artifactId' in item ? `${item.investigationTitle} · ${artifactKind(item)} · ${item.artifactId.slice(-12)}${items.includes(item) && item.match ? ` · matched ${item.match.field}` : ''}` : `${item.title} · ${item.status}`;
  }
  async function load(background = false) {
    const request = ++generation;
    if (!background) loading = true;
    error = '';
    try {
      const page = await savedWork.catalog(kind, query, cursor);
      if (request !== generation) return;
      items = page.items;
      next = page.nextCursor;
    } catch (cause) {
      if (request === generation) error = cause instanceof Error ? cause.message : String(cause);
    } finally { if (request === generation) loading = false; }
  }
  function find() { query = search.trim(); cursor = ''; previous = []; next = null; items = []; void load(); }
  function move(forward: boolean) {
    if (forward && next) { previous = [...previous, cursor]; cursor = next; }
    else if (!forward && previous.length) { cursor = previous.at(-1)!; previous = previous.slice(0, -1); }
    else return;
    items = [];
    void load();
  }
  onMount(() => {
    void load();
    const timer = setInterval(() => { if (active && !loading) void load(true); }, 15000);
    return () => { generation++; clearInterval(timer); };
  });
</script>

<div class="catalog-picker" data-catalog-kind={kind}>
  <form class="catalog-search" onsubmit={(event) => { event.preventDefault(); find(); }}>
    <label for={`${id}-search`}>{kind === 'artifacts' ? 'Search results by title, original question, or result text' : 'Search saved work by title'}</label>
    <div><input id={`${id}-search`} type="search" bind:value={search} disabled={disabled} placeholder={kind === 'artifacts' ? 'Remembered words or phrase' : 'All titles'} /><button type="submit" disabled={disabled}>Search</button></div>
  </form>
  <label for={id}>{label}</label>
  <select {id} {value} disabled={disabled || loading} aria-busy={loading} onchange={(event) => {
    selected = choices.find((item) => catalogKey(item) === event.currentTarget.value);
    onChoose(event.currentTarget.value, selected);
  }}>
    <option value="">{emptyLabel}</option>
    {#if value && !choices.some((item) => catalogKey(item) === value)}<option value={value}>{selectedLabel || value} · selected outside this page</option>{/if}
    {#each choices as item (catalogKey(item))}<option value={catalogKey(item)}>{itemLabel(item)}</option>{/each}
  </select>
  {#if kind === 'artifacts' && selection.item && 'artifactId' in selection.item}
    <div class="catalog-selection" data-selected-result={selection.item.artifactId}>
      {#if selection.onPage && selection.item.match}
        <p class="catalog-match" data-match-field={selection.item.match.field}><strong>Matched {selection.item.match.field}</strong><br />{selection.item.match.excerpt}</p>
      {:else if !selection.onPage}
        <p class="catalog-retained">Retained selection · outside this results page. Shown separately from this page’s search matches.</p>
      {/if}
      <p class="catalog-pin">Original input {selection.item.contextId}</p>
    </div>
  {/if}
  <nav aria-label={`${label} pages`}>
    <button type="button" disabled={disabled || loading || !previous.length} onclick={() => move(false)}>Previous page</button>
    <span role="status">{loading ? 'Loading…' : `Page ${previous.length + 1} · ${items.length} ${kind === 'artifacts' ? 'results' : 'investigations'}`}</span>
    <button type="button" disabled={disabled || loading || !next} onclick={() => move(true)}>Next page</button>
  </nav>
  {#if error}<p role="alert">{error} <button type="button" onclick={() => void load()}>Retry</button></p>{/if}
</div>

<style>
  .catalog-picker { min-width:0; margin-block:8px 14px; font-size:13px; }
  label { display:block; margin:8px 0 4px; }
  .catalog-search > div { display:flex; gap:6px; }
  input,select,button { box-sizing:border-box; min-width:0; font:inherit; color:var(--ink); background:var(--paper); border:1px solid var(--line-dark); padding:7px 8px; }
  input { flex:1; width:0; }
  select { width:100%; max-width:100%; }
  button { cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
  :is(input,select,button):focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  nav { display:flex; align-items:center; flex-wrap:wrap; gap:6px; margin-top:6px; }
  nav span { flex:1; min-width:90px; color:var(--muted); font-size:12px; }
  p { overflow-wrap:anywhere; color:var(--uncertain, var(--ink)); }
  .catalog-match { color:var(--ink); white-space:pre-wrap; }
  .catalog-pin { color:var(--muted); font:11px/1.5 monospace; }
  .catalog-retained { color:var(--muted); }
</style>
