export default function Pagination({ page, pageCount, onPageChange, isFetching }) {
  if (pageCount <= 1) return null
  return (
    <div className="pagination">
      <button className="secondary" disabled={page <= 1 || isFetching} onClick={() => onPageChange(page - 1)}>
        ← Previous
      </button>
      <span className="muted">
        Page {page.toLocaleString()} of {pageCount.toLocaleString()}
      </span>
      <button className="secondary" disabled={page >= pageCount || isFetching} onClick={() => onPageChange(page + 1)}>
        Next →
      </button>
    </div>
  )
}
