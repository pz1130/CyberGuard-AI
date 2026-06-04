import { createContext, useContext, useState } from 'react'
import type { Tab } from '../components/SidebarNew'

export interface SearchTarget {
  tab: Tab
  id: number | string
  name: string
  subview?: string
}

interface SearchContextValue {
  searchTarget: SearchTarget | null
  setSearchTarget: (t: SearchTarget | null) => void
}

export const SearchContext = createContext<SearchContextValue>({
  searchTarget: null,
  setSearchTarget: () => {},
})

export function SearchProvider({ children }: { children: React.ReactNode }) {
  const [searchTarget, setSearchTarget] = useState<SearchTarget | null>(null)
  return (
    <SearchContext.Provider value={{ searchTarget, setSearchTarget }}>
      {children}
    </SearchContext.Provider>
  )
}

export const useSearch = () => useContext(SearchContext)
