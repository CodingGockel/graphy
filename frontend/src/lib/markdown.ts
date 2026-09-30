import { marked } from 'marked'
import DOMPurify from 'dompurify'

// Links in LLM answers always open in a new tab.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node instanceof Element && node.tagName === 'A' && node.hasAttribute('href')) {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function renderMarkdown(text: string): string {
  const html = marked.parse(text, { gfm: true, async: false }) as string
  return DOMPurify.sanitize(html)
}
