import { Routes } from '@angular/router';

import { CefrE1 } from './cefr/cefr-e1';
import { ChatShell } from './chat/chat-shell';

export const routes: Routes = [
  { path: '', component: ChatShell },
  { path: 'cefr', component: CefrE1 },
];
