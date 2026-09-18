import { useContext } from 'react'
import type { ButtonHTMLAttributes } from 'react'
import { RoleContext, hasPermission } from '../context/permissions'

export function PermissionButton({ permission, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { permission: string }) {
  const role = useContext(RoleContext)
  return hasPermission(role, permission) ? <button {...props} /> : null
}
