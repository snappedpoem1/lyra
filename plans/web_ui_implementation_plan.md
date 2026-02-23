# Web UI Implementation Plan for Lyra Oracle

## Executive Summary

This document outlines the comprehensive plan to implement a full-featured web user interface for the Lyra Oracle music intelligence system. The web UI will expose all existing API functionality through an intuitive, modern interface while maintaining the powerful backend capabilities of the system.

## System Overview

The Lyra Oracle system consists of:
- Flask-based REST API with JSON responses
- SQLite database schema with migrations  
- Machine learning embeddings (CLAP) for dimensional scoring
- Music acquisition pipeline with multiple sources
- Semantic search capabilities using ChromaDB
- LLM-powered agent system for music intelligence
- Track structure analysis and radio recommendation engines

## API Endpoint Analysis

Based on the complete lyra_api.py file, there are 16 distinct functional areas that need to be exposed through the web UI:

### 1. Health & Status Endpoints
- `/health` - System health check
- `/api/status` - Detailed system status including LLM availability

### 2. Search Capabilities  
- `/api/search` - Semantic search endpoint
- `/api/search/hybrid` - Hybrid search with metadata filters and dimensional ranges

### 3. Library Management
- `/api/library/scan` - Trigger library scan
- `/api/library/index` - Trigger library indexing  
- `/api/library/tracks` - Get list of tracks

### 4. Vibes System
- `/api/vibes` - List all vibes
- `/api/vibes/save` - Create a new vibe
- `/api/vibes/build` - Build M3U8 for a vibe
- `/api/vibes/materialize` - Materialize a vibe as folder
- `/api/vibes/refresh` - Refresh vibe(s)
- `/api/vibes/delete` - Delete a vibe

### 5. Curation Tools
- `/api/curate/classify` - Classify all tracks
- `/api/curate/plan` - Generate curation plan  
- `/api/curate/apply` - Apply curation plan

### 6. Acquisition System
- `/api/acquire/youtube` - Download from YouTube
- `/api/acquire/queue` - Get acquisition queue
- `/api/acquire/process` - Process acquisition queue
- `/api/acquire/batch` - Start parallel batch download job
- `/api/acquire/batch/<job_id>/stream` - SSE stream for batch job progress
- `/api/acquire/batch/<job_id>/status` - Get batch job status
- `/api/downloads` - List downloads
- `/api/downloads/organize` - Organize downloads into library

### 7. Spotify Integration
- `/api/spotify/missing` - Find Spotify favorites not in local library
- `/api/spotify/stats` - Get Spotify import statistics

### 8. Scout & Lore Analysis
- `/api/scout/cross-genre` - Cross-genre hunt using Discogs + bridge artists
- `/api/lore/trace` - Trace artist lineage and store connections
- `/api/lore/connections` - Get stored connections for an artist

### 9. DNA Tracking
- `/api/dna/trace` - Trace samples for a track
- `/api/dna/pivot` - Pivot to original sample source if available

### 10. Hunter Acquisition
- `/api/hunter/hunt` - Hunt for a release via Prowlarr + Real-Debrid cache
- `/api/hunter/acquire` - Acquire a target from hunter results

### 11. Architect Track Structure Analysis
- `/api/architect/analyze` - Analyze track structure and store results
- `/api/structure/<track_id>` - Get stored structure analysis for a track

### 12. Radio Playback Recommendations
- `/api/radio/chaos` - Get chaos mode recommendations
- `/api/radio/flow` - Get flow mode recommendations  
- `/api/radio/discovery` - Get discovery mode recommendations
- `/api/radio/queue` - Build a full radio queue

### 13. Agent Query System
- `/api/agent/query` - Query Lyra agent for orchestration
- `/api/agent/fact-drop` - Get a fact drop for a track

### 14. Journal & Undo Operations
- `/api/journal` - Get operation history from journal
- `/api/undo` - Undo last N file operations

### 15. Pipeline Management
- `/api/pipeline/start` - Start acquisition pipeline
- `/api/pipeline/status/<job_id>` - Get pipeline job status  
- `/api/pipeline/run/<job_id>` - Execute pipeline for a job
- `/api/pipeline/jobs` - List recent pipeline jobs

### 16. Streaming Endpoints
- `/api/stream/<track_id>` - Stream audio file with Range support

## Frontend Architecture Design

### Technology Stack Recommendation

**Frontend Framework**: React.js with TypeScript
- Modern, component-based architecture
- Strong typing for better development experience
- Excellent ecosystem and community support

**State Management**: Redux Toolkit + RTK Query
- Built-in caching and optimistic updates
- Automatic API request management
- Type-safe state handling

**UI Components**: Material UI (MUI) v5
- Comprehensive component library
- Responsive design out of the box
- Accessible components with good documentation

**Routing**: React Router v6
- Declarative routing for SPA navigation
- Dynamic route matching and parameter parsing

**Styling**: CSS Modules + MUI Theme
- Component-scoped styling to avoid conflicts
- Consistent theming across application

### Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── layout/         # Header, Sidebar, Footer
│   ├── dashboard/      # Main dashboard views
│   ├── library/        # Library management components  
│   ├── vibes/          # Vibes system components
│   ├── curation/       # Curation tools
│   ├── acquisition/    # Acquisition pipeline UI
│   └── search/         # Search functionality
├── pages/              # Page-level components
│   ├── DashboardPage.tsx
│   ├── LibraryPage.tsx
│   ├── VibesPage.tsx
│   ├── CurationPage.tsx
│   ├── AcquisitionPage.tsx
│   ├── SearchPage.tsx
│   └── SettingsPage.tsx
├── services/           # API service layer
│   ├── apiClient.ts     # Axios instance with interceptors
│   ├── endpoints/       # API endpoint definitions
│   └── types/          # TypeScript interfaces for responses
├── store/              # Redux state management
│   ├── index.ts         # Store configuration
│   ├── slices/         # Redux slices for different domains
│   └── hooks/          # Custom React hooks for store access
├── utils/              # Utility functions and helpers
├── assets/             # Static assets (images, icons)
└── App.tsx            # Main application component
```

### Core Features Implementation Plan

#### 1. Dashboard & System Status
- Real-time system health monitoring
- Quick access to key operations
- Performance metrics display
- Recent activity timeline

#### 2. Library Management Interface  
- Track browsing with filtering/sorting capabilities
- Detailed track information view
- Batch operations for library maintenance
- Visual library statistics dashboard

#### 3. Vibes System UI
- Create, save, and manage vibe collections
- Preview and build M3U8 playlists
- Materialize vibes as folders for external use
- Refresh and delete functionality

#### 4. Curation Tools
- Track classification interface
- Curation plan generation wizard
- Apply curation actions with preview
- Visual planning tools

#### 5. Acquisition Pipeline
- YouTube download interface
- Queue management dashboard
- Batch job monitoring with progress indicators
- Download organization workflow
- Integration status for external services

#### 6. Search Functionality
- Semantic search with results display
- Hybrid search with advanced filters
- Dimensional scoring visualization
- Saved searches and favorites

#### 7. Spotify Integration
- Missing tracks discovery interface
- Import statistics dashboard
- Sync operations management

#### 8. Artist Analysis Tools
- Scout cross-genre hunting UI
- Lore artist connection tracing
- DNA sample tracking interface

#### 9. Radio Recommendations
- Chaos, flow, and discovery mode interfaces
- Queue building tools
- Playback recommendation visualization

#### 10. Agent System Interface
- LLM query interface with context management
- Fact drop display for tracks
- Conversation history management

#### 11. Operations Management
- Journal view with operation history
- Undo functionality with confirmation dialogs
- Pipeline job monitoring and control

## Implementation Phases

### Phase 1: Core Infrastructure (Weeks 1-2)
- Set up React project with TypeScript
- Configure routing system  
- Implement core layout components (Header, Sidebar, Footer)
- Create API service layer with RTK Query integration
- Design global state management structure
- Implement authentication and authorization flow

### Phase 2: Dashboard & System Status (Weeks 2-3) 
- Build main dashboard page
- Implement system health monitoring
- Create quick action buttons for common operations
- Add performance metrics display
- Set up real-time status updates

### Phase 3: Library Management (Weeks 3-4)
- Design track browsing interface
- Implement filtering and sorting capabilities  
- Create detailed track view modal
- Build batch operation tools
- Add library statistics dashboard

### Phase 4: Vibes System UI (Weeks 4-5)
- Create vibe management interface
- Implement save, build, materialize workflows
- Design refresh and delete functionality
- Add preview features for vibes

### Phase 5: Curation Tools (Weeks 5-6)
- Build classification workflow
- Implement curation plan generation UI  
- Create apply curation actions interface
- Add visual planning tools

### Phase 6: Acquisition Pipeline (Weeks 6-7)
- Design YouTube download interface
- Implement queue management dashboard
- Create batch job monitoring system
- Add download organization workflow
- Integrate external service status displays

### Phase 7: Search Functionality (Weeks 7-8)
- Build semantic search interface
- Implement hybrid search with filters
- Add dimensional scoring visualization
- Create saved searches functionality

### Phase 8: Advanced Features (Weeks 8-9)
- Spotify integration UI
- Artist analysis tools (Scout, Lore, DNA)
- Radio recommendations interfaces
- Agent system query interface
- Operations management dashboard

## Technical Considerations

### API Integration Patterns
1. **RTK Query for API Calls**: Use RTK Query's built-in caching and automatic refetching
2. **Error Handling**: Implement global error boundaries with user-friendly messages  
3. **Loading States**: Show loading spinners during API requests
4. **Progress Tracking**: For long-running operations like batch downloads

### Performance Optimization
1. **Virtualized Lists**: Use react-window for large track lists
2. **Code Splitting**: Lazy load heavy components
3. **Caching Strategies**: Implement appropriate caching for search results and static data
4. **Debounced Search**: Throttle search input to reduce API calls

### Security Considerations
1. **Input Validation**: Validate all user inputs before sending to backend
2. **Authentication**: Implement proper session management  
3. **Rate Limiting**: Prevent abuse of API endpoints
4. **Data Sanitization**: Clean data before display

## Database Access Patterns for Web Interface

The web UI will interact with the SQLite database through:
1. **API Endpoints**: All database operations are exposed via RESTful APIs
2. **Caching Layer**: RTK Query provides automatic caching of API responses  
3. **Real-time Updates**: SSE streams for long-running batch jobs
4. **Batch Operations**: Efficient bulk data handling where possible

## Implementation Effort Estimation

### Development Time Breakdown:
- Core infrastructure: 8-10 hours
- Dashboard & status: 12-15 hours  
- Library management: 15-20 hours
- Vibes system UI: 10-12 hours
- Curation tools: 12-15 hours
- Acquisition pipeline: 15-20 hours
- Search functionality: 10-15 hours
- Advanced features: 15-20 hours

### Total Estimated Effort: 100-130 hours

## Risk Mitigation Strategies

1. **API Stability**: Use RTK Query's built-in error handling and retry mechanisms
2. **Performance Issues**: Implement virtualization for large datasets, proper caching  
3. **Security Concerns**: Comprehensive input validation and authentication
4. **User Experience**: Design with responsive layouts and progressive enhancement principles

## Next Steps

1. Create React project structure
2. Set up API service layer with RTK Query integration
3. Implement core layout components
4. Begin building dashboard page with system status monitoring
5. Develop library management interface
6. Add search functionality
7. Implement acquisition pipeline UI
8. Build advanced features like vibes and curation tools

This plan provides a comprehensive roadmap for implementing a full-featured web UI that exposes all existing Lyra Oracle functionality while maintaining excellent user experience and performance.