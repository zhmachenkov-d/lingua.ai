import { Component } from '@angular/core';

import { ChatShell } from './chat/chat-shell';

@Component({
  imports: [ChatShell],
  selector: 'app-root',
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {}
