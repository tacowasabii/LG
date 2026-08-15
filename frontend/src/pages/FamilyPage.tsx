import { useEffect, useState } from 'react'
import { UserPlus, Users, X } from 'lucide-react'
import { getPersons, createPerson, PersonData } from '../lib/api'

export default function FamilyPage() {
  const [persons, setPersons] = useState<PersonData[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ name: '', relation: '', birth_year: '' })
  const [selectedPerson, setSelectedPerson] = useState<PersonData | null>(null)

  useEffect(() => {
    loadPersons()
  }, [])

  const loadPersons = async () => {
    try {
      const data = await getPersons()
      setPersons(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    if (!formData.name.trim()) return
    try {
      await createPerson({
        name: formData.name,
        relation: formData.relation,
        birth_year: formData.birth_year ? parseInt(formData.birth_year) : undefined,
      })
      setFormData({ name: '', relation: '', birth_year: '' })
      setShowForm(false)
      loadPersons()
    } catch (e) {
      console.error(e)
    }
  }

  const relationColors: Record<string, string> = {
    '아빠': 'bg-blue-100 text-blue-700',
    '엄마': 'bg-pink-100 text-pink-700',
    '아들': 'bg-green-100 text-green-700',
    '딸': 'bg-purple-100 text-purple-700',
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><p className="text-gray-400">불러오는 중...</p></div>
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">가족 구성원</h1>
          <p className="text-gray-500 mt-1">Memory Graph에 등록된 가족입니다.</p>
        </div>
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2">
          <UserPlus size={16} />
          추가
        </button>
      </div>

      {/* Add Form */}
      {showForm && (
        <div className="card border-primary-200 bg-primary-50/30">
          <h3 className="font-medium text-gray-800 mb-3">가족 구성원 추가</h3>
          <div className="grid grid-cols-3 gap-3">
            <input
              type="text"
              placeholder="이름"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <input
              type="text"
              placeholder="관계 (아빠, 엄마, 아들...)"
              value={formData.relation}
              onChange={(e) => setFormData({ ...formData, relation: e.target.value })}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <input
              type="number"
              placeholder="출생연도"
              value={formData.birth_year}
              onChange={(e) => setFormData({ ...formData, birth_year: e.target.value })}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={handleCreate} className="btn-primary text-sm">추가</button>
            <button onClick={() => setShowForm(false)} className="btn-secondary text-sm">취소</button>
          </div>
        </div>
      )}

      {/* Person Cards */}
      {persons.length === 0 ? (
        <div className="card text-center py-12">
          <Users size={40} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-400">등록된 가족 구성원이 없습니다.</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {persons.map((person) => (
            <div
              key={person.id}
              className="card hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => setSelectedPerson(person)}
            >
              <div className="flex items-center gap-4">
                {/* Avatar */}
                <div className="w-14 h-14 rounded-full bg-gray-100 flex items-center justify-center text-xl flex-shrink-0 overflow-hidden">
                  {person.thumbnail_url ? (
                    <img src={person.thumbnail_url} alt={person.name} className="w-full h-full object-cover" />
                  ) : (
                    person.name.charAt(0)
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-gray-900">{person.name}</h3>
                    {person.relation && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${relationColors[person.relation] || 'bg-gray-100 text-gray-600'}`}>
                        {person.relation}
                      </span>
                    )}
                  </div>
                  {person.birth_year && (
                    <p className="text-sm text-gray-500 mt-0.5">{person.birth_year}년생</p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Profile Modal */}
      {selectedPerson && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedPerson(null)}>
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full mx-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-end">
              <button onClick={() => setSelectedPerson(null)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>

            {/* Profile Image */}
            <div className="flex flex-col items-center mt-2">
              <div className="w-40 h-40 rounded-full overflow-hidden bg-gray-100 border-4 border-primary-100 shadow-lg">
                {selectedPerson.thumbnail_url ? (
                  <img src={selectedPerson.thumbnail_url} alt={selectedPerson.name} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-4xl text-gray-400">
                    {selectedPerson.name.charAt(0)}
                  </div>
                )}
              </div>

              <h2 className="text-xl font-bold text-gray-900 mt-4">{selectedPerson.name}</h2>
              {selectedPerson.relation && (
                <span className={`text-sm px-3 py-1 rounded-full mt-2 ${relationColors[selectedPerson.relation] || 'bg-gray-100 text-gray-600'}`}>
                  {selectedPerson.relation}
                </span>
              )}
              {selectedPerson.birth_year && (
                <p className="text-sm text-gray-500 mt-2">{selectedPerson.birth_year}년생</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
