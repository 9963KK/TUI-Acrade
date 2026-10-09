package launcher

import (
	"bytes"
	"errors"
	"io"
	"strings"
	"testing"
)

func TestForegroundTaskRestoresHandoffAfterFailure(t *testing.T) {
	want := errors.New("dependency failed")
	out := &bytes.Buffer{}
	task := &Task{Do: func(in io.Reader, output io.Writer) error {
		if !Quiet() {
			t.Fatal("platform handles interrupt during foreground operation")
		}
		raw, _ := io.ReadAll(in)
		output.Write(raw)
		return want
	}}
	task.SetStdin(strings.NewReader("input"))
	task.SetStdout(out)
	task.SetStderr(out)
	if err := task.Run(); !errors.Is(err, want) || out.String() != "input" {
		t.Fatal(err, out.String())
	}
	if handingOff.Load() {
		t.Fatal("failed operation did not release terminal")
	}
	defaultTask := &Task{Do: func(in io.Reader, out io.Writer) error {
		if in == nil || out == nil {
			t.Fatal("missing terminal streams")
		}
		return nil
	}}
	if err := defaultTask.Run(); err != nil {
		t.Fatal(err)
	}
}
