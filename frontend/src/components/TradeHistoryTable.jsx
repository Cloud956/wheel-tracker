import React, { useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'
import './Table.css'

const TradeHistoryTable = ({ data }) => {
  const columns = useMemo(
    () => [
      {
        accessorKey: 'date',
        header: 'Date',
      },
      {
        accessorKey: 'symbol',
        header: 'Symbol',
        cell: ({ getValue }) => <strong>{getValue()}</strong>,
      },
      {
        accessorKey: 'details',
        header: 'Details',
        cell: ({ getValue }) => (
          <span className="asset-details">{getValue()}</span>
        ),
      },
      {
        accessorKey: 'qty',
        header: 'Qty',
        cell: ({ getValue }) => (
          <span className={getValue() < 0 ? 'text-red' : 'text-green'}>
            {getValue()}
          </span>
        ),
      },
      {
        accessorKey: 'price',
        header: 'Price',
      },
      {
        accessorKey: 'comm',
        header: 'Comm',
        cell: ({ getValue }) => {
          const comm = getValue()
          return (
            <span className="text-red">
              {comm?.raw !== 0 ? comm?.value : '—'}
            </span>
          )
        },
      },
    ],
    []
  )

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    initialState: {
      sorting: [{ id: 'date', desc: true }],
    },
  })

  return (
    <div className="table-container">
      <table>
        <thead>
          {table.getHeaderGroups().map(headerGroup => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map(header => (
                <th
                  key={header.id}
                  onClick={header.column.getCanSort() ? header.column.getToggleSortingHandler() : undefined}
                  className={header.column.getCanSort() ? 'sortable' : ''}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {{
                    asc: ' ↑',
                    desc: ' ↓',
                  }[header.column.getIsSorted()] ?? null}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map(row => (
            <tr key={row.id}>
              {row.getVisibleCells().map(cell => (
                <td key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default TradeHistoryTable
