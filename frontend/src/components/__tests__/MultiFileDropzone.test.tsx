import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { MultiFileDropzone } from "@/components/ingestion/MultiFileDropzone"

const ACCEPT = ".xlsx,.pdf,.jpg,.jpeg,.png,.heic"

function makeFile(name: string, type: string, sizeKb = 1) {
  return new File(["x".repeat(sizeKb * 1024)], name, { type })
}

describe("MultiFileDropzone", () => {
  it("calls onChange with selected files", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<MultiFileDropzone files={[]} onChange={onChange} accept={ACCEPT} />)
    const input = screen.getByLabelText(/upload files/i) as HTMLInputElement
    await user.upload(input, [
      makeFile("a.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
      makeFile("b.pdf", "application/pdf"),
    ])
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ name: "a.xlsx" }),
      expect.objectContaining({ name: "b.pdf" }),
    ])
  })

  it("renders the file list with size and remove button", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const files = [makeFile("a.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 50)]
    render(<MultiFileDropzone files={files} onChange={onChange} accept={ACCEPT} />)
    expect(screen.getByText("a.xlsx")).toBeInTheDocument()
    expect(screen.getByText(/50.00 KB/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /remove a\.xlsx/i }))
    expect(onChange).toHaveBeenCalledWith([])
  })
})
