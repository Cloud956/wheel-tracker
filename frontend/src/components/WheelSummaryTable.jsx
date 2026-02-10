import React, { useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  getExpandedRowModel,
  flexRender,
} from '@tanstack/react-table'
import './Table.css'

const WheelSummaryTable = ({ data }) => {
  const [pagination, setPagination] = useState({
    pageIndex: 0,
    pageSize: 10,
  })
  const [expanded, setExpanded] = useState({})

  const columns = useMemo(
    () => [
      {
        id: 'expander',
        header: () => null,
        cell: ({ row }) => (
          <button
            onClick={(e) => {
              e.stopPropagation() // Prevent row selection if that exists
              row.toggleExpanded()
            }}
            style={{ cursor: 'pointer', background: 'none', border: 'none', color: '#fff', fontSize: '1.2em', padding: '0 5px' }}
          >
            {row.getIsExpanded() ? '▼' : '▶'}
          </button>
        ),
        size: 40,
        enableSorting: false,
      },
      {
        accessorKey: 'wheelNum',
        header: '#',
        size: 60,
        enableSorting: true,
      },
      {
        accessorKey: 'symbol',
        header: 'Symbol',
        enableSorting: true,
        cell: ({ getValue }) => <strong>{getValue()}</strong>,
      },
      {
        accessorKey: 'strike',
        header: 'Strike',
        enableSorting: true,
      },
      {
        accessorKey: 'startDate',
        header: 'Start',
        enableSorting: true,
      },
      {
        accessorKey: 'endDate',
        header: 'End',
        enableSorting: true,
        cell: ({ row }) => row.original.isOpen ? '—' : row.original.endDate,
      },
      {
        accessorKey: 'comm',
        header: 'Comms',
        enableSorting: true,
        cell: ({ getValue }) => (
          <span className="text-red">{getValue()?.value || '—'}</span>
        ),
      },
      {
        accessorKey: 'pnl',
        header: 'Net Result',
        enableSorting: true,
        cell: ({ getValue }) => {
          const pnl = getValue()
          return (
            <span className={pnl?.class || ''}>
              {pnl?.value || '—'}
            </span>
          )
        },
      },
      {
        accessorKey: 'isOpen',
        header: 'Status',
        enableSorting: true,
        cell: ({ getValue }) => getValue() ? 'ACTIVE' : 'CLOSED',
      },
    ],
    []
  )

  const table = useReactTable({
    data: data || [],
    columns,
    getRowId: row => String(row.wheelNum), // Use wheelNum as unique ID string
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    onPaginationChange: setPagination,
    onExpandedChange: setExpanded,
    state: {
      pagination,
      expanded,
    },
    initialState: {
      sorting: [{ id: 'wheelNum', desc: true }],
      pagination: {
        pageSize: 10,
      },
    },
    enableSorting: true,
  })

  return (
    <div className="table-container">
      <table>
        <thead>
          {table.getHeaderGroups().map(headerGroup => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map(header => {
                const canSort = header.column.getCanSort()
                return (
                  <th
                    key={header.id}
                    style={{ width: header.getSize() }}
                    onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                    className={canSort ? 'sortable' : ''}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {canSort && (
                        <span>
                          {{
                            asc: ' ↑',
                            desc: ' ↓',
                          }[header.column.getIsSorted()] ?? ' ⇅'}
                        </span>
                      )}
                    </div>
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map(row => (
            <React.Fragment key={row.id}>
              <tr
                className={row.original.isOpen ? 'row-active' : ''}
              >
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
              {row.getIsExpanded() && (
                <tr>
                  <td colSpan={row.getVisibleCells().length} style={{ padding: 0 }}>
                    <div className="expanded-row-content" style={{ padding: '15px', backgroundColor: '#2a2a40', borderTop: '1px solid #444' }}>
                      <h4 style={{ margin: '0 0 10px 0', color: '#ccc' }}>Trades for Wheel #{row.original.wheelNum}</h4>
                      <table style={{ width: '100%', fontSize: '0.85em', background: 'transparent' }}>
                        <thead>
                          <tr style={{ background: '#333' }}>
                            <th style={{ padding: '8px' }}>Date</th>
                            <th style={{ padding: '8px' }}>Action</th>
                            <th style={{ padding: '8px' }}>Details</th>
                            <th style={{ padding: '8px' }}>Type</th>
                            <th style={{ padding: '8px' }}>Quantity</th>
                            <th style={{ padding: '8px' }}>Price</th>
                          </tr>
                        </thead>
                        <tbody>
                          {row.original.trades && row.original.trades.map((trade, idx) => (
                            <tr key={idx} style={{ background: idx % 2 === 0 ? 'rgba(255,255,255,0.05)' : 'transparent' }}>
                              <td style={{ padding: '8px', borderBottom: '1px solid #444' }}>{trade.date}</td>
                              <td style={{ padding: '8px', borderBottom: '1px solid #444' }}>{trade.action}</td>
                              <td style={{ padding: '8px', borderBottom: '1px solid #444' }}>{trade.details}</td>
                              <td style={{ padding: '8px', borderBottom: '1px solid #444' }}>{trade.type}</td>
                              <td style={{ padding: '8px', borderBottom: '1px solid #444' }} className={trade.quantity < 0 ? 'text-red' : 'text-green'}>
                                {trade.quantity}
                              </td>
                              <td style={{ padding: '8px', borderBottom: '1px solid #444' }} className={trade.price?.class}>
                                {trade.price?.value}
                              </td>
                            </tr>
                          ))}
                          {(!row.original.trades || row.original.trades.length === 0) && (
                            <tr>
                              <td colSpan={6} style={{ padding: '10px', textAlign: 'center', color: '#888' }}>
                                No trades found for this wheel.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
      <div className="pagination">
        <div className="pagination-info">
          Showing {table.getState().pagination.pageIndex * table.getState().pagination.pageSize + 1} to{' '}
          {Math.min(
            (table.getState().pagination.pageIndex + 1) * table.getState().pagination.pageSize,
            table.getFilteredRowModel().rows.length
          )}{' '}
          of {table.getFilteredRowModel().rows.length} entries
        </div>
        <div className="pagination-controls">
          <div className="page-size-selector">
            <label htmlFor="page-size">Show:</label>
            <select
              id="page-size"
              value={table.getState().pagination.pageSize}
              onChange={(e) => {
                table.setPageSize(Number(e.target.value))
              }}
            >
              {[10, 25, 50].map((pageSize) => (
                <option key={pageSize} value={pageSize}>
                  {pageSize}
                </option>
              ))}
            </select>
          </div>
          <div className="page-navigation">
            <button
              onClick={() => table.setPageIndex(0)}
              disabled={!table.getCanPreviousPage()}
              className="pagination-button"
            >
              {'<<'}
            </button>
            <button
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              className="pagination-button"
            >
              {'<'}
            </button>
            <span className="page-info">
              Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
            </span>
            <button
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              className="pagination-button"
            >
              {'>'}
            </button>
            <button
              onClick={() => table.setPageIndex(table.getPageCount() - 1)}
              disabled={!table.getCanNextPage()}
              className="pagination-button"
            >
              {'>>'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default WheelSummaryTable
