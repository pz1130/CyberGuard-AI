import { useState, type ReactNode } from 'react'
import { SearchContext, type SearchTarget } from './search'

export function SearchProvider({ children }: { children: ReactNode }) {
  const [searchTarget, setSearchTarget] = useState<SearchTarget | null>(null)
  return (
    <SearchContext.Provider value={{ searchTarget, setSearchTarget }}>
      {children}
    </SearchContext.Provider>
  )
}
