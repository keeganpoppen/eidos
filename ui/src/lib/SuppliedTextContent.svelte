<script lang="ts">
  import type { LocalTextEvidence } from './types';
  let { text, evidence }: { text: string; evidence: LocalTextEvidence } = $props();
  let full = $state(false);
</script>

<section class="supplied-text-content" data-supplied-text-id={evidence.id} aria-label="Supplied text">
  <p class="classification">Supplied text · {evidence.fileName}</p>
  <p class="origin">Local file; contents supplied by the owner.</p>
  <pre>{full ? text : text.slice(0, 12000)}</pre>
  {#if text.length > 12000}<button class="work-secondary" onclick={() => full = !full}>{full ? 'Collapse supplied text' : 'Read complete supplied text'}</button>{/if}
  {#if text.length === 0}<p>The supplied file is empty.</p>{/if}
  <details><summary>File identity and saved provenance</summary>
    <p class="object-ref">{evidence.byteLength} original bytes<br />File SHA-256 {evidence.fileSha256}<br />Saved record SHA-256 {evidence.hostRecordSha256}<br />Admission {evidence.id}<br />{evidence.parserVersion}</p>
    <p>This records supplied file contents, not proof of their origin or execution.</p>
  </details>
</section>

<style>
  .supplied-text-content { min-width:0; overflow-wrap:anywhere; }
  p { font-size:14px; line-height:1.5; }
  .classification { color:var(--accent); }
  .origin { color:var(--muted); }
  pre { max-height:440px; max-width:100%; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; padding:12px; border:1px solid var(--line); background:var(--code); font:13px/1.55 monospace; }
  details { margin:14px 0; font-size:13px; }
  summary { cursor:pointer; }
  summary:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
  .object-ref { font:12px/1.6 monospace; }
</style>
