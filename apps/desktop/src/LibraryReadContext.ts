import { createContext } from 'react';

// 每轮读取捕获库代次；独立使用的组件保持原有读取行为。
export const LibraryReadContext = createContext<() => () => boolean>(() => () => true);
