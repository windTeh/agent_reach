(async () => {
  // Traverse React fiber tree to find story-related data with duration
  const results = [];
  
  function findFiberNodes(el, depth = 0) {
    if (depth > 15 || results.length > 20) return;
    const keys = Object.keys(el);
    const fiberKey = keys.find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
    if (!fiberKey) return;
    
    const fiber = el[fiberKey];
    function traverse(node, d) {
      if (!node || d > 10 || results.length > 20) return;
      
      // Check memoizedProps for duration or story data
      const props = node.memoizedProps;
      if (props) {
        const propsStr = JSON.stringify(props);
        if (propsStr && (propsStr.includes('duration') || propsStr.includes('video_duration') || propsStr.includes('18117072050489215'))) {
          // Found relevant data - extract key info
          const durMatch = propsStr.match(/"duration[^"]*":\s*(\d+)/);
          const contentMatch = propsStr.match(/18117072050489215/);
          results.push({
            type: node.type?.name || node.type?.displayName || typeof node.type,
            hasDuration: !!durMatch,
            durationVal: durMatch ? durMatch[1] : null,
            hasContentId: !!contentMatch,
            propsSnippet: propsStr.slice(0, 300)
          });
        }
      }
      
      // Check memoizedState
      const state = node.memoizedState;
      if (state && state.memoizedState) {
        const stateStr = JSON.stringify(state.memoizedState);
        if (stateStr && (stateStr.includes('duration') || stateStr.includes('18117072050489215'))) {
          const durMatch = stateStr.match(/"duration[^"]*":\s*(\d+)/);
          results.push({
            type: 'state:' + (node.type?.name || typeof node.type),
            hasDuration: !!durMatch,
            durationVal: durMatch ? durMatch[1] : null,
            stateSnippet: stateStr.slice(0, 300)
          });
        }
      }
      
      // Traverse children
      if (node.child) traverse(node.child, d + 1);
      if (node.sibling) traverse(node.sibling, d + 1);
    }
    
    traverse(fiber, 0);
  }
  
  // Find React root and traverse
  const allEls = document.querySelectorAll('div');
  for (const el of allEls) {
    const keys = Object.keys(el);
    const fiberKey = keys.find(k => k.startsWith('__reactFiber$'));
    if (fiberKey) {
      const fiber = el[fiberKey];
      // Check if this is a root fiber (no parent or parent is null)
      if (!fiber.return) {
        // This is a root, traverse from here
        function traverseFromRoot(node, d) {
          if (!node || d > 20 || results.length > 30) return;
          
          const props = node.memoizedProps;
          if (props) {
            try {
              const propsStr = JSON.stringify(props);
              if (propsStr.includes('duration') && propsStr.length < 50000) {
                const durMatches = [];
                const re = /"duration[^"]*":\s*(\d+)/g;
                let m;
                while ((m = re.exec(propsStr)) !== null) {
                  durMatches.push({ key: m[0], ctx: propsStr.slice(Math.max(0, m.index - 30), m.index + m[0].length + 10).slice(0, 80) });
                }
                if (durMatches.length > 0) {
                  results.push({
                    type: node.type?.name || node.type?.displayName || typeof node.type,
                    depth: d,
                    durMatches: durMatches.slice(0, 5)
                  });
                }
              }
            } catch(e) {}
          }
          
          if (node.child) traverseFromRoot(node.child, d + 1);
          if (node.sibling) traverseFromRoot(node.sibling, d + 1);
        }
        traverseFromRoot(fiber, 0);
        if (results.length > 0) break;
      }
    }
  }
  
  return JSON.stringify({ count: results.length, items: results.slice(0, 10) });
})()
