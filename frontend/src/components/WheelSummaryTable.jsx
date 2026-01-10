import React, { useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'
import './Table.css'

const WheelSummaryTable = ({ data }) => {
  const columns = useMemo(
    () => [
      {
        accessorKey: 'wheelNum',
        header: '#',
        size: 60,
      },
      {
        accessorKey: 'symbol',
        header: 'Symbol',
        cell: ({ getValue }) => <strong>{getValue()}</strong>,
      },
      {
        accessorKey: 'strike',
        header: 'Strike',
      },
      {
        accessorKey: 'startDate',
        header: 'Start',
      },
      {
        accessorKey: 'endDate',
        header: 'End',
        cell: ({ row }) => row.original.isOpen ? '—' : row.original.endDate,
      },
      {
        accessorKey: 'comm',
        header: 'Comms',
        cell: ({ getValue }) => (
          <span className="text-red">{getValue()?.value || '—'}</span>
        ),
      },
      {
        accessorKey: 'pnl',
        header: 'Net Result',
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
        cell: ({ getValue }) => getValue() ? 'ACTIVE' : 'CLOSED',
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
      sorting: [{ id: 'wheelNum', desc: true }],
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
                  style={{ width: header.getSize() }}
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
            <tr
              key={row.id}
              className={row.original.isOpen ? 'row-active' : ''}
            >
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

export default WheelSummaryTable
