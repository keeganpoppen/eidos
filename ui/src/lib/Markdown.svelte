<script lang="ts">
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';

  let { source = '' }: { source?: string } = $props();

  const rendered = $derived(
    DOMPurify.sanitize(
      marked.parse(source, {
        gfm: true,
        breaks: false
      }) as string
    )
  );
</script>

<div class="markdown">
  {@html rendered}
</div>
