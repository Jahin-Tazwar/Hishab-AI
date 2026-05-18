import Superscript from "@tiptap/extension-superscript"
import { EditorContent, useEditor } from "@tiptap/react"
import StarterKit from "@tiptap/starter-kit"
import { useEffect } from "react"

import { cn } from "@/lib/utils"

interface Props {
  value: string                          // HTML
  onChange: (html: string) => void
  disabled?: boolean
}

export function DraftEditor({ value, onChange, disabled }: Props) {
  const editor = useEditor({
    extensions: [StarterKit, Superscript],
    content: value,
    editable: !disabled,
    onUpdate({ editor }) {
      onChange(editor.getHTML())
    },
    editorProps: {
      attributes: {
        class: cn(
          "min-h-[24rem] rounded-md border p-4 focus:outline-none",
          "[&_sup.citation]:text-blue-600 [&_sup.citation]:font-semibold",
        ),
      },
    },
  })

  // Keep editor content in sync if `value` changes from outside (e.g. regenerate)
  useEffect(() => {
    if (editor && value !== editor.getHTML()) {
      editor.commands.setContent(value, { emitUpdate: false })
    }
  }, [value, editor])

  useEffect(() => {
    editor?.setEditable(!disabled)
  }, [editor, disabled])

  return <EditorContent editor={editor} />
}
