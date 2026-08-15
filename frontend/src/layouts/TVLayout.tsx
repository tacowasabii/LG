import { Outlet } from 'react-router-dom'

export default function TVLayout() {
  return (
    <div className="h-screen w-screen bg-black overflow-hidden">
      <Outlet />
    </div>
  )
}
