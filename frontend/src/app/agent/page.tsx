"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { 
  Bot, 
  Play, 
  Pause, 
  Settings, 
  Activity,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Zap
} from "lucide-react";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useAgentStatus, useAgentLogs, useUpdateAgentStatus } from "@/hooks/useApi";
import { formatDate, formatRelativeTime } from "@/lib/utils";
import type { AgentStatus } from "@/types";

export default function AgentPage() {
  const { data: status } = useAgentStatus();
  const { data: agentLogs = [] } = useAgentLogs(20);
  const updateStatusMutation = useUpdateAgentStatus();
  const [agentStatus, setAgentStatus] = useState<AgentStatus>({
    isRunning: true,
    autoJobDiscovery: true,
    autoResumeGeneration: true,
    autoApply: false,
    dailyApplicationLimit: 10,
    matchScoreThreshold: 75,
  });

  useEffect(() => {
    if (status) {
      setAgentStatus(status);
    }
  }, [status]);

  const statusColors = {
    completed: "text-green-400",
    running: "text-blue-400",
    failed: "text-red-400",
    pending: "text-yellow-400",
  };

  const statusIcons = {
    completed: CheckCircle,
    running: Loader2,
    failed: XCircle,
    pending: Clock,
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Automation Agent</h1>
            <p className="text-muted-foreground">Control your AI career automation agent</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={agentStatus.isRunning ? "success" : "secondary"} className="gap-1">
              <span className={`h-2 w-2 rounded-full ${agentStatus.isRunning ? "bg-green-400" : "bg-gray-400"}`} />
              {agentStatus.isRunning ? "Running" : "Paused"}
            </Badge>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Automation Controls */}
          <div className="lg:col-span-2 space-y-6">
            {/* Status Card */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bot className="h-5 w-5 text-primary" />
                  Automation Status
                </CardTitle>
                <CardDescription>Control agent automation features</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Toggle Controls */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium">Auto Job Discovery</p>
                      <p className="text-sm text-muted-foreground">Automatically search for new jobs</p>
                    </div>
                    <Switch 
                      checked={agentStatus.autoJobDiscovery}
                      onCheckedChange={(checked) => {
                        setAgentStatus({ ...agentStatus, autoJobDiscovery: checked });
                        updateStatusMutation.mutate({ autoJobDiscovery: checked });
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium">Auto Resume Generation</p>
                      <p className="text-sm text-muted-foreground">Generate tailored resumes automatically</p>
                    </div>
                    <Switch 
                      checked={agentStatus.autoResumeGeneration}
                      onCheckedChange={(checked) => {
                        setAgentStatus({ ...agentStatus, autoResumeGeneration: checked });
                        updateStatusMutation.mutate({ autoResumeGeneration: checked });
                      }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium">Auto Apply</p>
                      <p className="text-sm text-muted-foreground">Automatically apply to matching jobs</p>
                    </div>
                    <Switch 
                      checked={agentStatus.autoApply}
                      onCheckedChange={(checked) => {
                        setAgentStatus({ ...agentStatus, autoApply: checked });
                        updateStatusMutation.mutate({ autoApply: checked });
                      }}
                    />
                  </div>
                </div>

                {/* Settings */}
                <div className="pt-4 border-t border-white/10">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm font-medium block mb-2">
                        Daily Application Limit
                      </label>
                      <input 
                        type="number" 
                        value={agentStatus.dailyApplicationLimit}
                        onChange={(e) => {
                          const value = parseInt(e.target.value);
                          setAgentStatus({ ...agentStatus, dailyApplicationLimit: value });
                          updateStatusMutation.mutate({ dailyApplicationLimit: value });
                        }}
                        className="w-full px-3 py-2 rounded-lg bg-card border border-white/10"
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium block mb-2">
                        Match Score Threshold (%)
                      </label>
                      <input 
                        type="number" 
                        value={agentStatus.matchScoreThreshold}
                        onChange={(e) => {
                          const value = parseInt(e.target.value);
                          setAgentStatus({ ...agentStatus, matchScoreThreshold: value });
                          updateStatusMutation.mutate({ matchScoreThreshold: value });
                        }}
                        className="w-full px-3 py-2 rounded-lg bg-card border border-white/10"
                      />
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex gap-2 pt-4">
                  <Button className="gap-2">
                    <Play className="h-4 w-4" />
                    Run Agent Cycle
                  </Button>
                  <Button variant="outline" className="gap-2">
                    <Pause className="h-4 w-4" />
                    Pause Automation
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Activity Logs */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="h-5 w-5 text-green-400" />
                  Activity Logs
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {agentLogs.map((log) => {
                    const StatusIcon = statusIcons[log.status];
                    return (
                      <div 
                        key={log.id} 
                        className="flex items-center justify-between p-3 rounded-lg bg-white/5"
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${
                            log.status === 'completed' ? 'bg-green-500/20' :
                            log.status === 'running' ? 'bg-blue-500/20' :
                            log.status === 'failed' ? 'bg-red-500/20' :
                            'bg-yellow-500/20'
                          }`}>
                            <StatusIcon className={`h-4 w-4 ${statusColors[log.status]} ${log.status === 'running' ? 'animate-spin' : ''}`} />
                          </div>
                          <div>
                            <p className="font-medium">{log.task}</p>
                            <p className="text-xs text-muted-foreground">{log.details}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-muted-foreground">{log.duration}</p>
                          <p className="text-xs text-muted-foreground">{formatRelativeTime(log.timestamp)}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Agent Health */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Zap className="h-5 w-5 text-yellow-400" />
                  Agent Health
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Uptime</span>
                    <Badge variant="success">99.9%</Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Last Run</span>
                    <span className="text-sm text-muted-foreground">2 minutes ago</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Tasks Today</span>
                    <span className="text-sm font-medium">12</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm">Success Rate</span>
                    <Badge variant="success">95%</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Quick Stats */}
            <Card>
              <CardHeader>
                <CardTitle>This Week</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                    <span className="text-sm">Jobs Scraped</span>
                    <span className="font-bold text-primary">42</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                    <span className="text-sm">Resumes Generated</span>
                    <span className="font-bold text-green-400">8</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                    <span className="text-sm">Applications Sent</span>
                    <span className="font-bold text-purple-400">12</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                    <span className="text-sm">Follow-ups Sent</span>
                    <span className="font-bold text-yellow-400">5</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
