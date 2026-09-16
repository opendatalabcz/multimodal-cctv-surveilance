import Box from '@mui/material/Box'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface AssistantMarkdownProps {
  content: string
}

export function AssistantMarkdown({ content }: AssistantMarkdownProps) {
  return (
    <Box
      sx={{
        fontSize: '1rem',
        lineHeight: 1.5,
        '& p': { m: 0, mb: 1, '&:last-child': { mb: 0 } },
        '& strong': { fontWeight: 700 },
        '& em': { fontStyle: 'italic' },
        '& ul, & ol': { m: 0, mb: 1, pl: 2.5, '&:last-child': { mb: 0 } },
        '& li': { mb: 0.5 },
        '& h1, & h2, & h3, & h4, & h5, & h6': {
          mt: 1,
          mb: 0.75,
          fontSize: '1.05rem',
          fontWeight: 700,
          '&:first-of-type': { mt: 0 },
        },
        '& code': {
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
          fontSize: '0.875em',
          bgcolor: 'action.hover',
          px: 0.5,
          borderRadius: 0.5,
        },
        '& pre': {
          overflow: 'auto',
          p: 1,
          mb: 1,
          bgcolor: 'action.hover',
          borderRadius: 1,
          '&:last-child': { mb: 0 },
        },
        '& pre code': { bgcolor: 'transparent', p: 0 },
        '& a': { color: 'inherit', textDecoration: 'underline' },
        '& table': { borderCollapse: 'collapse', width: '100%', mb: 1 },
        '& th, & td': {
          border: '1px solid',
          borderColor: 'divider',
          px: 1,
          py: 0.5,
          textAlign: 'left',
        },
        '& blockquote': {
          m: 0,
          mb: 1,
          pl: 1.5,
          borderLeft: '3px solid',
          borderColor: 'divider',
        },
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          img: () => null,
        }}
      >
        {content}
      </ReactMarkdown>
    </Box>
  )
}
