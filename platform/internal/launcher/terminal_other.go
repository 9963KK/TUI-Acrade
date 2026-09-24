//go:build !darwin && !linux && !windows

package launcher

import (
	"os"
	"os/exec"
)

var handoffSignals = []os.Signal{os.Interrupt}

func writeReset() { os.Stdout.WriteString(Reset) }

type noState struct{}

func saveTerminal() *noState                 { return nil }
func restoreTerminal(*noState)               {}
func signalCode(*exec.ExitError) (int, bool) { return 0, false }
