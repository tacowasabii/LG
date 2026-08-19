/**
 * EXAONE 답변에 섞여 오는 **굵게** 와 `코드` 표기만 렌더한다.
 *
 * 마크다운 전체를 지원하지 않는다. 문자열을 조각내 React 노드로 만들기 때문에
 * HTML 주입 경로가 없다 (dangerouslySetInnerHTML을 쓰지 않는다).
 *
 * LLM이 생성한 텍스트를 화면에 그리는 곳마다 이걸 써야 한다.
 * 채팅 답변, 인터뷰 질문, TV 내레이션이 모두 같은 모델에서 나온다.
 */
export default function RichText({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)

  return (
    <>
      {parts.map((part, i) => {
        if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
          return <strong key={i}>{part.slice(2, -2)}</strong>
        }
        if (part.length > 2 && part.startsWith('`') && part.endsWith('`')) {
          return (
            <code key={i} className="px-1 py-0.5 bg-gray-100 text-gray-700 rounded text-[13px]">
              {part.slice(1, -1)}
            </code>
          )
        }
        return part
      })}
    </>
  )
}
